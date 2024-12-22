# Clothes monitor

A simple script I wrote to track the prices of clothes from specific websites.

Scrapes the site for the price and sends an email with a price summary. Price history is saved in a database file. Same day entries are deleted.

Works best when automatically run daily.

## Requirements

A gmail account from which emails may be sent is required. To login to the account,
an [application password](https://support.google.com/accounts/answer/185833?hl=en) must be set up for the account and placed in a file.

## Usage

Install the required python modules

`pip install -r requirements.txt`

Run using the following command after appropriately specifying details in the sender and receiver json files

`python monitor.py -sj example_sender.json -jf example_receiver`

(multiple receiver files may be passed simultaneously).
