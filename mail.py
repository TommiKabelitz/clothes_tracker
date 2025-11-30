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
<html>
  <body style="font-family: Arial, sans-serif; font-size: 16px; color: #333; line-height: 1.6;">
    <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px; border-radius: 8px;">
      
      <p>Hello <strong>{person}</strong>,</p>
      
      <p>Hopefully you have some sales today! Here are the price updates for the items you are tracking:</p>

      {contents}

      <p>Best,<br>Your Price Tracker xx</p>

      <hr style="margin-top: 30px; border: none; border-top: 1px solid #ccc;">
      <p style="font-size: 13px; color: #888;">Reply to this email with feedback or questions.</p>
    </div>
  </body>
</html>
"""

history_template = """
<ul style="margin: 0; padding-left: 20px;">
  <li><strong>Mean Price:</strong> {mean_price}</li>
  <li><strong>Mode Price:</strong> {mode_price}</li>
  <li><strong>On Sale Proportion:</strong> {on_sale_proportion:.2f} ({on_sale_count}/{num_entries})</li>
  <li><strong>Last on Sale:</strong> {last_sale}</li>
</ul>
"""

summary_template = """
<div style="margin-bottom: 20px; padding: 10px; border: 1px solid #eee; border-radius: 6px; {box_style}">
  {sale_badge}
  <a href="{url}" style="color: #1a0dab; text-decoration: none;">{url}</a><br><br>

  {history_summary}

  <p><strong>Current Price:</strong> {price}<br>
     {discount_info}</p>

  {image_block}
</div>
"""

url_invalid_template = """
<div style="border: 1px solid #ff0000; padding: 8px;">
  <div style="color: #ff0000; font-weight: bold;">
    This item either no longer exists or has moved to a different url. (It is possible this colour is simply not listed anymore). Please send me an updated link so I can update it.
  </div>
  <div style="margin-top: 4px; word-break: break-all;">
    {url}
  </div>
</div>
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
    msg.set_content("This email contains HTML. Please view in a client that supports HTML.")
    msg.add_alternative(contents, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        server.login(sender_details["address"], password)
        server.send_message(msg)
