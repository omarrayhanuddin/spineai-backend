from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.services.email_service import send_email
import os
from datetime import datetime
from typing import Dict, Any
from app.core.config import settings
router = APIRouter(prefix="/v1/email", tags=["Email"])

@router.post("/send-ebook")
async def send_ebook_email(recipient: str) -> Dict[str, str]:
    """
    Send e-book purchase confirmation email with PDF attachment
    """
    try:
        pdf_path = os.path.join("app", "static", "files", "ebook.pdf")
        
        # Check if PDF file exists
        if not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=404,
                detail="E-book PDF file not found"
            )

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
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send e-book email: {str(e)}"
        )

@router.post("/send-image-credits")
async def send_image_credits_email(
    recipient: str,
    credit_amount: int = 20,
    background_tasks: BackgroundTasks = BackgroundTasks()
) -> Dict[str, Any]:
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
@router.post("/send-credit-limit-notification")
async def send_credit_limit_notification(
    recipient: str,
    remaining_credits: int = 0,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """
    Send notification when user's image credits are exhausted
    Parameters:
    - recipient: Email address to send to
    - remaining_credits: Credits left (typically 0)
    """
    try:
        context = {
            "remaining_credits": remaining_credits,
            "purchase_url": f"{settings.FRONTEND_URL}/purchase/credits",  
            "account_url": f"{settings.FRONTEND_URL}/account",
            "support_email": "support@spineai.com",
            "company_name": "SpineAi",
            "current_year": datetime.now().year
        }

        background_tasks.add_task(
            send_email,
            subject="Your Image Credits Have Been Used Up",
            recipient=recipient,
            template_name="credit_limit_notification.html",
            context=context
        )

        return {
            "message": f"Credit limit notification sent to {recipient}",
            "remaining_credits": remaining_credits
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send credit limit notification: {str(e)}"
        )