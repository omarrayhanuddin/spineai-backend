# app/api/routes/email.py

from fastapi import APIRouter, HTTPException
from app.services.email_service import send_email
from fastapi import BackgroundTasks
import os
from datetime import datetime

router = APIRouter(prefix="/v1/email", tags=["Email"])

@router.post("/send-ebook")
async def send_ebook_email(recipient: str):
    pdf_path = os.path.join("app", "static", "files", "ebook.pdf")

    context = {
        "coupon_code": "SAVE20",
        "discount_percentage": "20%",
        "support_email": "support@spineai.com",
        "company_name": "SpineAi",
        "current_year": datetime.now().year
    }

    await send_email(
        subject="Your E-Book Purchase & Discount Coupon",
        recipient=recipient,
        template_name="ebook_purchase.html", 
        context=context,
        attachments=[pdf_path]
    )

    return {"message": f"E-book email sent to {recipient}"}

@router.post("/send-image-credits")
async def send_image_credits_email(
    recipient: str,
    credit_amount: int = 20,  # Default to 20 credits
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Send image credits purchase confirmation email
    Parameters:
    - recipient: Email address to send to
    - credit_amount: Number of credits purchased (10, 20, or 50)
    """
    try:
        # Validate credit amount
        if credit_amount not in [10, 20, 50]:
            raise HTTPException(
                status_code=400,
                detail="Invalid credit amount. Must be 10, 20, or 50"
            )

        context = {
            "credit_amount": credit_amount,
            "support_email": "support@spineai.com",
            "company_name": "SpineAi",
            "current_year": datetime.now().year
        }

        # Send email via background task
        background_tasks.add_task(
            send_email,
            subject=f"Your {credit_amount} Image Credits Purchase",
            recipient=recipient,
            template_name="image_credits_purchase.html",
            context=context
        )

        return {
            "message": f"Image credits email queued for {recipient}",
            "credit_amount": credit_amount
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send image credits email: {str(e)}"
        )