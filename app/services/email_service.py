# app/services/mail_service.py

from app.core.config import settings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.mime.base import MIMEBase
from email import encoders
from jinja2 import Environment, FileSystemLoader
import aiosmtplib
from datetime import date
import os
from typing import List, Optional

template_env = Environment(loader=FileSystemLoader("app/templates"))

async def send_email(
    subject: str, 
    recipient: str, 
    template_name: str, 
    context: dict, 
    attachments: Optional[List[str]] = None
):
    current_year = str(date.today().year)
    context["current_year"] = current_year

    template = template_env.get_template(template_name)
    html_content = template.render(context)

    sender_name = "SpineAi"
    message = MIMEMultipart("mixed")
    message["From"] = f"{sender_name} <{settings.FROM_EMAIL}>"
    message["To"] = recipient
    message["Subject"] = subject

    # HTML part
    message.attach(MIMEText(html_content, "html"))

    # Handle attachments
    if attachments:
        for attachment_path in attachments:
            if os.path.exists(attachment_path):
                with open(attachment_path, "rb") as file:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(file.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={os.path.basename(attachment_path)}",
                    )
                    message.attach(part)

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=True,
    )