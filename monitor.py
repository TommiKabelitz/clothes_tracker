import argparse
import json
from datetime import datetime
import logging
import bs4
import requests
import pandas as pd
import smtplib
import ssl


LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format=f"(%(name)s(%(lineno)4d)::%(levelname)-8s: %(message)s",
)
database_file = "tracker.db"
url_ID_file = "urls.txt"

mail_template = """
Subject: Your Daily Price Update


Hello {person},

Hopefully you have some sales today! Here are the price updates for the items you are tracking:

{contents}

Best,
Your Price Tracker x

Reply to this email with feedback or questions.
"""


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
    return vars(parser.parse_args())


class URLIDs:
    def __init__(self):
        self._ID_as_key = {}
        self._url_as_key = {}

    @property
    def IDs(self):
        return self._ID_as_key

    @property
    def urls(self):
        return self._url_as_key

    def add_ID(self, ID: int, url: str):
        self._ID_as_key[int(ID)] = url
        self._url_as_key[url] = int(ID)


def get_url_IDs() -> URLIDs:
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
    with open(url_ID_file, "w") as f:
        for ID, url in url_IDs.IDs.items():
            f.write(f"{ID} {url}\n")


def assign_ID_to_new(url_IDs: URLIDs, new_url: str):
    if new_url not in url_IDs.urls:
        try:
            new_ID = max(url_IDs.IDs.keys()) + 1
        except ValueError:
            new_ID = 0
        url_IDs.add_ID(new_ID, new_url)
        return new_ID


def load_database():
    try:
        return pd.read_csv(database_file)
    except FileNotFoundError:
        LOGGER.info("No existing database found, creating new one.")
        return pd.DataFrame(columns=["url_ID", "price", "compare_price", "date"])


def write_database_file(todays_entrys: dict, database: pd.DataFrame):
    df = pd.DataFrame(todays_entrys)
    database = pd.concat([database, df], ignore_index=True).drop_duplicates()
    database.to_csv(database_file, mode="w", header=True, index=False)


def get_price_history(database: pd.DataFrame, todays_entrys: dict):
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


def send_email(person: str, contact: str, contents: str, sender_details: dict):
    LOGGER.debug(f"Sending email to {person} at {contact} with contents:\n{contents}")

    port = 465
    with open(sender_details["password_file"], "r") as f:
        password = f.read().strip()
    context = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        server.login(sender_details["address"], password)
        email_content = mail_template.format(person=person, contents=contents)
        server.sendmail(sender_details["address"], contact["email"], email_content)


def convert_prices(*args: str):
    return [float(arg.replace("$", "")) if arg is not None else None for arg in args]


def main(json_files: list, sender_json: str):

    sender_details = json.load(open(sender_json, "r"))

    url_IDs = get_url_IDs()
    LOGGER.debug(f"URL IDs: {url_IDs.urls}")
    database = load_database()
    LOGGER.debug(f"Database: {database}")

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

    todays_entrys = {"url_ID": [], "price": [], "compare_price": [], "date": []}
    for url, (people, site) in url_dict.items():
        if url not in url_IDs.urls:
            assign_ID_to_new(url_IDs, url)
        url_ID = url_IDs.urls[url]
        price, compare_price = site_checkers[site](url)
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

    price_history = get_price_history(database, todays_entrys)
    item_summaries = {}
    for i, url_ID in enumerate(todays_entrys["url_ID"]):
        if price_history[url_ID] is not None:
            history_summary = f"""
Mean Price: {price_history[url_ID]["mean_price"]}
Mode Price: {price_history[url_ID]["mode_price"]}
On Sale Proportion: {price_history[url_ID]["on_sale_count"]/price_history[url_ID]["num_entries"]} ({price_history[url_ID]["on_sale_count"]}/{price_history[url_ID]["num_entries"]})
Last on Sale: {price_history[url_ID]["last_sale"]}
            """
        else:
            history_summary = "No history available (new item to tracker)."
        summary = f"""
{url_ID}: {url_IDs.IDs[url_ID]}
{history_summary}
Current Price: {todays_entrys["price"][i]}
Is on Sale: {todays_entrys["compare_price"][i] is not None}
        """
        if todays_entrys["compare_price"][i] is not None:
            summary += f"Discounted from: {todays_entrys['compare_price'][i]}\n"
        item_summaries[url_ID] = summary

    for person, (contact, urls) in details_dict.items():
        contents = [item_summaries[url_IDs.urls[url]] for url in urls]
        send_email(person, contact, "\n\n".join(contents), sender_details)


def kookai_checker(url: str):

    LOGGER.debug(f"Checking: \n{url}")
    data = requests.get(url)
    if "Page Not Found" in data.text:
        LOGGER.error("Page Not Found")
        raise requests.HTTPError

    soup = bs4.BeautifulSoup(data.text, "html.parser")
    try:
        all_divs = soup.find_all("div", attrs={"class": "product__price-container"})
    except Exception:
        LOGGER.error(
            "There was an error trying to identify HTML elements on the webpage."
        )
    for div in all_divs:
        for tag in div.children:
            if not hasattr(tag, "attrs"):
                continue
            if "class" not in tag.attrs:
                continue
            if "product__price" in tag["class"]:
                price = tag.text
            if "product__compare-at-price" in tag["class"]:
                compare_price = tag.text if tag.text != "" else None
        LOGGER.debug(f"Found price to be {price} with compare price {compare_price}")
    return price, compare_price


site_checkers = {
    "kookai": kookai_checker,
}

if __name__ == "__main__":
    input_args = Input()
    if input_args.pop("verbose"):
        LOGGER.setLevel(logging.DEBUG)
    main(**input_args)
