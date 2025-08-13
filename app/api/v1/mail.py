# app/api/routes/email.py

from fastapi import APIRouter
from app.services.mail_service import send_email
import os

router = APIRouter(prefix="/v1/email", tags=["Email"])

@router.post("/send-ebook")
async def send_ebook_email(recipient: str):
    pdf_path = os.path.join("app", "static", "files", "ebook.pdf")

    context = {
        "coupon_code": "SAVE20",
        "discount_percentage": "20%",
        "support_email": "support@spineai.com",
        "company_name": "SpineAi"
    }

    await send_email(
        subject="Your E-Book Purchase & Discount Coupon",
        recipient=recipient,
        template_name="ebook_purchase.html", 
        context=context,
        pdf_path=pdf_path
    )

    return {"message": f"Email sent to {recipient}"}
