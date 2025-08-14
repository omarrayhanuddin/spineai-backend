# app/services/mail_service.py

from app.core.config import settings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from jinja2 import Environment, FileSystemLoader
import aiosmtplib
from datetime import date
import os

template_env = Environment(loader=FileSystemLoader("app/templates"))

async def send_email(subject: str, recipient: str, template_name: str, context: dict, pdf_path: str = None):
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

    # Optional PDF attachment
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as pdf_file:
            pdf_attachment = MIMEApplication(pdf_file.read(), _subtype="pdf")
            pdf_attachment.add_header(
                "Content-Disposition", "attachment", filename=os.path.basename(pdf_path)
            )
            message.attach(pdf_attachment)

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=True,
    )
