from app.core.config import settings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Environment, FileSystemLoader
import aiosmtplib
from datetime import date


# Set up Jinja2 environment
template_env = Environment(loader=FileSystemLoader("app/templates"))


async def send_email(subject: str, recipient: str, template_name: str, context: dict):
    # Load and render the HTML template
    current_year = str(date.today().year)
    context["current_year"] = current_year
    template = template_env.get_template(template_name)
    html_content = template.render(context)
    sender_name = "SpineAi"
    # Create the email message
    message = MIMEMultipart("alternative")
    message["From"] = f"{sender_name} <{settings.FROM_EMAIL}>\n"
    message["To"] = recipient
    message["Subject"] = subject
    message.attach(MIMEText(html_content, "html"))

    # Send the email asynchronously
    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=True,
    )
