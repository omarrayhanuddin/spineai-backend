from fastapi import APIRouter, Depends, HTTPException
from app.api.dependency import get_current_user
from app.models.user import User
from app.models.payment import Plan
from app.core.config import settings
from datetime import datetime

router = APIRouter(prefix="/v1/notifications", tags=["Notifications"])

@router.get("/credit-limit-notification")
async def credit_limit_notification(
    user: User = Depends(get_current_user)
):
    """
    Check user's image generation limit status
    Response scenarios:
    1. No plan purchased
    2. Low image credits (<5 remaining)
    3. No image credits (0 remaining)
    4. Sufficient image credits
    """
    if not user.current_plan:
        return {
            "status": "no_plan",
            "message": "You haven't purchased any plan yet",
            "action": {
                "text": "Browse Plans",
                "url": f"{settings.FRONTEND_URL}/plans"
            },
            "limits": {
                "image_limit": 0,
                "remaining_images": 0
            },
            "timestamp": datetime.now().isoformat()
        }
    
    image_limit = user.current_plan.image_limit
    used_images = getattr(user, "used_images", 0)
    remaining_images = max(0, image_limit - used_images)
    
    if remaining_images <= 0:
        return {
            "status": "no_credits",
            "message": "You have no image generation credits remaining",
            "action": {
                "text": "Purchase Credits",
                "url": f"{settings.FRONTEND_URL}/purchase/credits"
            },
            "limits": {
                "image_limit": image_limit,
                "remaining_images": 0,
                "used_images": used_images
            },
            "timestamp": datetime.now().isoformat()
        }
    elif remaining_images < 5:
        return {
            "status": "low_credits",
            "message": f"Low image generation credits remaining ({remaining_images} left)",
            "action": {
                "text": "Top Up Credits",
                "url": f"{settings.FRONTEND_URL}/purchase/credits"
            },
            "limits": {
                "image_limit": image_limit,
                "remaining_images": remaining_images,
                "used_images": used_images
            },
            "timestamp": datetime.now().isoformat()
        }
    
    return {
        "status": "sufficient_credits",
        "message": f"You have {remaining_images} image generation credits available",
        "limits": {
            "image_limit": image_limit,
            "remaining_images": remaining_images,
            "used_images": used_images
        },
        "timestamp": datetime.now().isoformat()
    }