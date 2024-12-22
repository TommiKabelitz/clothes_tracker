import argparse
import json
from datetime import datetime
import logging

import pandas as pd

import mail, site_scrapers

local_modules = [mail, site_scrapers]

LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format=f"(%(name)s(%(lineno)4d)::%(levelname)-8s: %(message)s",
)

database_file = "tracker.db"
url_ID_file = "urls.txt"


def Input():
    parser = argparse.ArgumentParser(
        description="Monitor a list of URLs for price changes."
    )
    parser.add_argument(
        "-sj",
        "--sender-json",
        type=str,
        required=True,
        help="A json file containing the sender's information.",
    )
    parser.add_argument(
        "-jf",
        "--json-files",
        type=str,
        required=True,
        nargs="*",
        help="A list of json files containing receiver and site information.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Include debugging information in logs.",
    )
    parser.add_argument(
        "-ne",
        "--no-email",
        action="store_true",
        help="Do not send emails.",
    )
    return vars(parser.parse_args())


class URLIDs:
    """Simple 2 directional dictionary for URL to ID and ID to URL."""
    # Didn't bother inheriting from a dict or similar because
    # we can always access the sub-dicts for the same functionality.
    # eg. for looping
    def __init__(self):
        self._ID_as_key = {}
        self._url_as_key = {}

    @property
    def ID_as_key(self):
        return self._ID_as_key

    @property
    def url_as_key(self):
        return self._url_as_key

    def add_ID(self, ID: int, url: str):
        self._ID_as_key[int(ID)] = url
        self._url_as_key[url] = int(ID)


def get_url_IDs() -> URLIDs:
    """Get the url IDs from the file, or create a new one if it doesn't exist."""
    try:
        with open(url_ID_file, "r") as f:
            lines = f.read()
    except FileNotFoundError:
        LOGGER.info("No URL IDs file found, creating new one.")
        return URLIDs()
    lines = lines[:-1] if lines[-1] == "\n" else lines
    url_IDs = URLIDs()
    for line in lines.split("\n"):
        url_IDs.add_ID(*line.split(" "))
    return url_IDs


def write_url_IDs(url_IDs: URLIDs):
    """Write the URL IDs to the file."""
    with open(url_ID_file, "w") as f:
        for ID, url in url_IDs.ID_as_key.items():
            f.write(f"{ID} {url}\n")


def assign_ID_to_new(url_IDs: URLIDs, new_url: str) -> int | None:
    """Assign a new ID to a URL if it doesn't already have one. Return the new ID if a new one is created, else None."""
    if new_url not in url_IDs.url_as_key:
        try:
            new_ID = max(url_IDs.ID_as_key.keys()) + 1
        except ValueError:
            new_ID = 0
        url_IDs.add_ID(new_ID, new_url)
        return new_ID


def load_database():
    """Load the database from the file, or create an empty DataFrame with labelled columns."""
    try:
        return pd.read_csv(database_file, parse_dates=["date"])
    except FileNotFoundError:
        LOGGER.info("No existing database found, creating new one.")
        df = pd.DataFrame(columns=["url_ID", "price", "compare_price", "date"])
        return df


def write_database_file(todays_entrys: dict, database: pd.DataFrame):
    """Convert today's entrys to a DataFrame, remove duplicates, and write to file."""
    df = pd.DataFrame(todays_entrys)
    # Throws a warning when df["compare_price"] is all NaN. Should be fine.
    database = pd.concat([database, df], ignore_index=True)
    database["date"] = pd.to_datetime(database["date"])
    database = database.drop_duplicates(ignore_index=True) # Has issues if date formats are inconsistent
    database.to_csv(
        database_file, mode="w", header=True, index=False, date_format="%Y/%m/%d"
    )


def get_price_history(database: pd.DataFrame, todays_entrys: dict):
    """Compile the mean and mode prices, on sale status, and last sale date for each URL ID."""
    history = {}
    for url_ID in todays_entrys["url_ID"]:
        if url_ID in database["url_ID"]:
            subset = database[database["url_ID"] == url_ID]
            on_sale = subset[subset["compare_price"].notna()]
            history[url_ID] = dict(
                mean_price=subset["price"].mean(),
                mode_price=subset["price"].mode().iloc[0],
                on_sale_count=len(on_sale),
                last_sale=on_sale["date"].max(),
                num_entries=len(subset),
            )
        else:
            history[url_ID] = None
    return history


def convert_prices(*args: str) -> list[float]:
    """Drop $ from prices and convert to float. Accepts arbitrary number of arguments."""
    return [float(arg.replace("$", "")) if arg is not None else None for arg in args]


def main(json_files: list, sender_json: str, no_email: bool = False):

    sender_details = json.load(open(sender_json, "r"))

    url_IDs = get_url_IDs()
    LOGGER.debug(f"URL IDs: {url_IDs.url_as_key}")
    database = load_database()
    LOGGER.debug(f"Database: {database}")

    # Get all the URLs and the people tracking them
    url_dict = {}
    details_dict = {}
    for json_file in json_files:
        LOGGER.info(f"Checking {json_file}")
        with open(json_file, "r") as file:
            data = json.load(file)
        personal_urls = []
        person, contact = data["person"], data["contact"]
        for site, urls in data["sites"].items():
            for url in urls:
                if url not in url_dict:
                    url_dict[url] = ([person], site)
                else:
                    url_dict[url][0].append(person)
                personal_urls.append(url)
        details_dict[person] = contact, personal_urls

    # Get the prices for each URL
    todays_entrys = {"url_ID": [], "price": [], "compare_price": [], "date": []}
    for url, (people, site) in url_dict.items():
        if url not in url_IDs.url_as_key:
            assign_ID_to_new(url_IDs, url)
        url_ID = url_IDs.url_as_key[url]
        price, compare_price = getattr(site_scrapers, site)(url)
        price, compare_price = convert_prices(price, compare_price)
        todays_entrys["url_ID"].append(url_ID)
        todays_entrys["price"].append(price)
        todays_entrys["compare_price"].append(compare_price)
    todays_entrys["date"] = [
        pd.to_datetime(datetime.today().strftime("%Y-%m-%d"))
    ] * len(todays_entrys["url_ID"])
    LOGGER.debug(f"Today's entrys: {todays_entrys}")
    LOGGER.debug(f"URL IDs: {url_IDs}")

    write_url_IDs(url_IDs)
    write_database_file(todays_entrys, database)

    # Write the summary for each item
    price_history = get_price_history(database, todays_entrys)
    item_summaries = {}
    for i, url_ID in enumerate(todays_entrys["url_ID"]):
        if price_history[url_ID] is not None:
            history_summary = mail.history_template.format(
                mean_price=price_history[url_ID]["mean_price"],
                mode_price=price_history[url_ID]["mode_price"],
                on_sale_proportion=price_history[url_ID]["on_sale_count"]
                / price_history[url_ID]["num_entries"],
                on_sale_count=price_history[url_ID]["on_sale_count"],
                num_entries=price_history[url_ID]["num_entries"],
                last_sale=price_history[url_ID]["last_sale"],
            )

        else:
            history_summary = "No history available (new item to tracker)."
        summary = mail.summary_template.format(
            url_ID=url_ID,
            url=url_IDs.ID_as_key[url_ID],
            history_summary=history_summary,
            price=todays_entrys["price"][i],
            is_on_sale=todays_entrys["compare_price"][i] is not None,
        )

        if todays_entrys["compare_price"][i] is not None:
            summary += f"Discounted from: {todays_entrys['compare_price'][i]}\n"
        item_summaries[url_ID] = summary

    if no_email:
        return
    # Send emails with the summaries they are tracking
    for person, (contact, urls) in details_dict.items():
        contents = [item_summaries[url_IDs.url_as_key[url]] for url in urls]
        mail.send_email(person, contact, "\n\n".join(contents), sender_details)


if __name__ == "__main__":
    input_args = Input()
    if input_args.pop("verbose"):
        LOGGER.setLevel(logging.DEBUG)
        for mod in local_modules:
            mod.LOGGER.setLevel(logging.DEBUG)
    main(**input_args)
