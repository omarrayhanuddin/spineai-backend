from fastapi import APIRouter, Depends, HTTPException
from app.api.dependency import get_current_user
from app.models.user import User
from app.core.config import settings
from datetime import datetime

router = APIRouter(prefix="/v1/notifications", tags=["Notifications"])

@router.get("/credit-limit-notification")
async def credit_limit_notification(
    user: User = Depends(get_current_user)
):
    """
    Check user's credit status and return appropriate notification message
    Response scenarios:
    1. No plan purchased
    2. Low credits (<5)
    3. No credits (0)
    4. Sufficient credits
    """
    if not user.current_plan:
        return {
            "status": "no_plan",
            "message": "You haven't purchased any plan yet",
            "action": {
                "text": "Browse Plans",
                "url": f"{settings.FRONTEND_URL}/plans"
            },
            "timestamp": datetime.now().isoformat()
        }
    
    # Assuming your Plan model has image_credits field
    credits = getattr(user.current_plan, "image_credits", 0)
    
    if credits <= 0:
        return {
            "status": "no_credits",
            "message": "You have no image credits remaining",
            "action": {
                "text": "Purchase Credits",
                "url": f"{settings.FRONTEND_URL}/purchase/credits"
            },
            "remaining_credits": 0,
            "timestamp": datetime.now().isoformat()
        }
    elif credits < 5:
        return {
            "status": "low_credits",
            "message": f"Low image credits remaining ({credits} left)",
            "action": {
                "text": "Top Up Credits",
                "url": f"{settings.FRONTEND_URL}/purchase/credits"
            },
            "remaining_credits": credits,
            "timestamp": datetime.now().isoformat()
        }
    
    return {
        "status": "sufficient_credits",
        "message": f"You have {credits} image credits available",
        "remaining_credits": credits,
        "timestamp": datetime.now().isoformat()
    }