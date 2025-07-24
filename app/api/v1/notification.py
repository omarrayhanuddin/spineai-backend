from fastapi import APIRouter, Depends, HTTPException, status
from app.models.notification import Notification
from app.schemas.notification import NotificationOut, NotifcationUpdate
from app.api.v1.user import get_current_user

router = APIRouter(prefix="/v1/notification", tags=["Notification Endpoints"])


@router.get("/all", response_model=list[NotificationOut])
async def get_all_notifications(
    user=Depends(get_current_user), limit: int = 10, offset: int = 0
):
    return (
        await Notification.filter(user=user)
        .offset(offset)
        .limit(limit)
        .order_by("-created_at")
    )


@router.post("/update-read")
async def update_read_notifications(
    form: NotifcationUpdate, user=Depends(get_current_user)
):
    await Notification.filter(id__in=form.ids, user=user).update(is_read=True)
    return {"message": "Notifications updated successfully"}
