from __future__ import annotations
import argparse
import json
from datetime import datetime
import logging
import sqlite3

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
    """Get the url IDs from the database."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    cursor.execute("SELECT url_ID, url FROM url_ids")
    rows = cursor.fetchall()
    conn.close()
    url_IDs = URLIDs()
    for url_ID, url in rows:
        url_IDs.add_ID(url_ID, url)
    return url_IDs


def write_url_IDs(url_IDs: URLIDs):
    """Write the URL IDs to the database."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    for url_ID, url in url_IDs.ID_as_key.items():
        cursor.execute(
            """
            INSERT OR IGNORE INTO url_ids (url_ID, url)
            VALUES (?, ?)
            """,
            (url_ID, url),
        )
    conn.commit()
    conn.close()


def assign_ID_to_new(url_IDs: URLIDs, new_url: str) -> int | None:
    """Assign a new ID to a URL if it doesn't already have one. Return the new ID if a new one is created, else None."""
    if new_url not in url_IDs.url_as_key:
        try:
            new_ID = max(url_IDs.ID_as_key.keys()) + 1
        except ValueError:
            new_ID = 0
        url_IDs.add_ID(new_ID, new_url)
        # Insert the new mapping into the database
        conn = sqlite3.connect(database_file)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO url_ids (url_ID, url)
            VALUES (?, ?)
            """,
            (new_ID, new_url),
        )
        conn.commit()
        conn.close()
        return new_ID


def initialise_database():
    """Initialise the SQLite database and create tables if they don't exist."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tracker (
            url_ID INTEGER,
            price REAL,
            compare_price REAL,
            date TEXT,
            PRIMARY KEY (url_ID, date)
        )
        """
    )
    # Create url_ids table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS url_ids (
            url_ID INTEGER PRIMARY KEY,
            url TEXT UNIQUE
        )
        """
    )
    conn.commit()
    conn.close()


def write_database(todays_entrys: dict):
    """Insert today's entries into the SQLite database."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    for i in range(len(todays_entrys["url_ID"])):
        cursor.execute(
            """
            INSERT OR IGNORE INTO tracker (url_ID, price, compare_price, date)
            VALUES (?, ?, ?, ?)
            """,
            (
                todays_entrys["url_ID"][i],
                todays_entrys["price"][i],
                todays_entrys["compare_price"][i],
                todays_entrys["date"][i].strftime("%Y-%m-%d"),
            ),
        )
    conn.commit()
    conn.close()


def get_price_history(todays_entrys: dict):
    """Compile the mean and mode prices, on sale status, and last sale date for each URL ID."""
    conn = sqlite3.connect(database_file)
    cursor = conn.cursor()
    history = {}
    for url_ID in todays_entrys["url_ID"]:
        cursor.execute(
            """
            SELECT price, compare_price, date
            FROM tracker
            WHERE url_ID = ?
            """,
            (url_ID,),
        )
        rows = cursor.fetchall()
        if rows:
            prices = [row[0] for row in rows]
            compare_prices = [row[1] for row in rows if row[1] is not None]
            dates = [row[2] for row in rows]
            history[url_ID] = dict(
                mean_price=sum(prices) / len(prices),
                mode_price=max(set(prices), key=prices.count),
                on_sale_count=len(compare_prices),
                last_sale=max(dates) if compare_prices else None,
                num_entries=len(prices),
            )
        else:
            history[url_ID] = None
    conn.close()
    return history


def convert_prices(*args: str) -> list[float]:
    """Drop $ from prices and convert to float. Accepts arbitrary number of arguments."""
    return [
        float(arg.replace("$", "").replace("AUD", "")) if arg is not None else None
        for arg in args
    ]


def main(json_files: list, sender_json: str, no_email: bool = False):
    initialise_database()
    sender_details = json.load(open(sender_json, "r"))

    url_IDs = get_url_IDs()
    LOGGER.debug(f"URL IDs: {url_IDs.url_as_key}")

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
    todays_entrys = {
        "url_ID": [],
        "price": [],
        "compare_price": [],
        "image_urls": [],
        "date": [],
    }
    for url, (people, site) in url_dict.items():
        if url not in url_IDs.url_as_key:
            assign_ID_to_new(url_IDs, url)
        url_ID = url_IDs.url_as_key[url]
        price, compare_price, image_urls = getattr(site_scrapers, site)(url)
        price, compare_price = convert_prices(price, compare_price)
        todays_entrys["url_ID"].append(url_ID)
        todays_entrys["price"].append(price)
        todays_entrys["compare_price"].append(compare_price)
        todays_entrys["image_urls"].append(image_urls)
    todays_entrys["date"] = [datetime.today()] * len(todays_entrys["url_ID"])
    LOGGER.debug(f"Today's entrys: {todays_entrys}")
    LOGGER.debug(f"URL IDs: {url_IDs}")

    write_url_IDs(url_IDs)
    write_database(todays_entrys)

    # Write the summary for each item
    price_history = get_price_history(todays_entrys)
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

        image_url = (
            todays_entrys["image_urls"][i][0]
            if todays_entrys["image_urls"][i]
            else None
        )
        image_block = (
            f'<img src="{image_url}" alt="Product Image" style="max-height: 150px; width: auto; border-radius: 4px; margin-top: 10px;">'
            if image_url
            else ""
        )

        is_on_sale = todays_entrys["compare_price"][i] is not None
        box_style = "background-color: #e6ffe6;" if is_on_sale else ""
        sale_badge = (
            '<div style="background-color: #28a745; color: white; padding: 4px 8px; display: inline-block; border-radius: 4px; font-size: 14px; margin-bottom: 10px;">On Sale!</div>'
            if is_on_sale
            else ""
        )
        discount_info = (
            f"<strong>Discounted from:</strong> {todays_entrys['compare_price'][i]}"
        )
        summary = mail.summary_template.format(
            url_ID=url_ID,
            url=url_IDs.ID_as_key[url_ID],
            history_summary=history_summary,
            price=todays_entrys["price"][i],
            is_on_sale=is_on_sale,
            image_block=image_block,
            box_style=box_style,
            sale_badge=sale_badge,
            discount_info=discount_info,
        )

        item_summaries[url_ID] = summary

    if no_email:
        return
    # Send emails with the summaries they are tracking
    for person, (contact, urls) in details_dict.items():
        contents = [item_summaries[url_IDs.url_as_key[url]] for url in urls]
        email_html = mail.mail_template.format(
            person=person, contents="".join(contents)
        )
        mail.send_email(person, contact, email_html, sender_details)


if __name__ == "__main__":
    input_args = Input()
    if input_args.pop("verbose"):
        LOGGER.setLevel(logging.DEBUG)
        for mod in local_modules:
            mod.LOGGER.setLevel(logging.DEBUG)
    main(**input_args)
