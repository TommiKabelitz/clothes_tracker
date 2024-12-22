"""
Functions for scraping various websites. Should return a price and a compare price.
Compare price is the un-discounted price when the item is on sale.
"""

import logging

import bs4
import requests

LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format=f"(%(name)s(%(lineno)4d)::%(levelname)-8s: %(message)s",
)


def kookai(url: str) -> tuple[str, str | None]:
    """
    Kookai website scraper.

    Kookai has a field "compare-at-price" which is non-null when the item is on sale.

    Args:
        url (str): The URL to scrape.

    Returns:
        tuple: The price (current buying price) and compare price (un-discounted price when on sale, otherwise None).
    """
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
