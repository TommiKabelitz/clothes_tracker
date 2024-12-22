from datetime import datetime
import email
import logging
import smtplib
import ssl

LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format=f"(%(name)s(%(lineno)4d)::%(levelname)-8s: %(message)s",
)


mail_template = """
Hello {person},

Hopefully you have some sales today! Here are the price updates for the items you are tracking:

{contents}

Best,
Your Price Tracker x

Reply to this email with feedback or questions.
"""

history_template = """
Mean Price: {mean_price}
Mode Price: {mode_price}
On Sale Proportion: {on_sale_proportion} ({on_sale_count}/{num_entries})
Last on Sale: {last_sale}
"""

summary_template = """
{url}
{history_summary}
Current Price: {price}
Is on Sale: {is_on_sale}
"""


def send_email(person: str, contact: dict, contents: str, sender_details: dict):
    """
    Send an email to a person.

    Utilises the google smtp server to send an email to the contact with the contents.
    The sender details must include a password file that contains an application password
    for the sender's email address.

    Parameters
    ----------
    person : str
        Name of the receiver of the email.
    contact : str
        Contact details of the receiver. Should contain an email address under 'email'.
    contents : str
        The contents of the email.
    sender_details : dict
        Details of the sender email address. Must contain 'address' and 'password_file'.
    """
    LOGGER.debug(f"Sending email to {person} at {contact} with contents:\n{contents}")

    port = 465
    with open(sender_details["password_file"], "r") as f:
        password = f.read().strip()

    context = ssl.create_default_context()

    msg = email.message.EmailMessage()
    msg["Subject"] = (
        f"Your Daily Price Update - {datetime.today().strftime('%Y-%m-%d')}"
    )
    msg["From"] = sender_details["address"]
    msg["To"] = contact["email"]
    msg.set_content(mail_template.format(person=person, contents=contents))

    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        server.login(sender_details["address"], password)
        server.send_message(msg)
