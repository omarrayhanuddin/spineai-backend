from fastapi import APIRouter, Depends
from app.api.dependency import get_current_admin
from app.models.user import User
from app.models.payment import PurchasedItem
from app.schemas.payment import PurchasedItemOut
from app.tasks.chat import (
    send_recommendations_notification,
    create_treatment_plan_from_ai_response,
    send_daily_treatment_notification,
    async_db_operation_for_treatment_notify,
    async_db_operation_for_recommendations_notify,
    async_db_operation_for_treatment_plan,
)
from datetime import datetime, timedelta
from app.tasks.product import async_db_get_ai_recommendation, get_ai_tags_per_session

router = APIRouter(prefix="/v1/admin", tags=["Admin Endpoints"])


@router.get("/dashboard", dependencies=[Depends(get_current_admin)])
async def get_dashboard_data():
    today = datetime.now().date()
    start_of_day = datetime.combine(today, datetime.min.time())
    end_of_day = datetime.combine(today, datetime.max.time())

    start_of_month = today.replace(day=1)
    start_of_next_month = (start_of_month.replace(day=28) + timedelta(days=4)).replace(
        day=1
    )

    return {
        "total_users": await User.all().count(),
        "total_free_users": await User.filter(current_plan__isnull=True).count(),
        "total_paid_users": await User.filter(current_plan__isnull=False).count(),
        "total_registered_user_today": await User.filter(
            created_at__gte=start_of_day, created_at__lte=end_of_day
        ).count(),
        "total_registered_user_this_month": await User.filter(
            created_at__gte=start_of_month, created_at__lt=start_of_next_month
        ).count(),
    }


# test send recommendations notification
@router.post("/send-recommendations-notification")
async def send_recommendations_notification_endpoint(
    current_admin: dict = Depends(get_current_admin), function_only: bool = False
):
    if function_only:
        await async_db_operation_for_recommendations_notify()
        return {"message": "Function only."}
    send_recommendations_notification.delay()
    return {"message": "Recommendations notification task queued."}


# test create treatment plan from ai response
@router.post("/create-treatment-plan-from-ai-response")
async def create_treatment_plan_from_ai_response_endpoint(
    current_admin: dict = Depends(get_current_admin), function_only: bool = False
):
    if function_only:
        await async_db_operation_for_treatment_plan()
        return {"message": "Function only."}
    create_treatment_plan_from_ai_response.delay()
    return {"message": "Treatment plan creation task queued."}


# test send daily treatment notification
@router.post("/send-daily-treatment-notification")
async def send_daily_treatment_notification_endpoint(
    current_admin: dict = Depends(get_current_admin), function_only: bool = False
):
    if function_only:
        await async_db_operation_for_treatment_notify()
        return {"message": "Daily treatment notification task queued."}
    send_daily_treatment_notification.delay()
    return {"message": "Daily treatment notification task queued."}


@router.post("/send-create-product-tags")
async def send_create_product_tags_endpoint(
    current_admin: dict = Depends(get_current_admin),
    session_id: str = None,
    function_only: bool = False,
):
    if not session_id:
        return {"error": "Session ID is required."}

    if function_only:
        await async_db_get_ai_recommendation(session_id)
        return {"message": "Function only."}

    get_ai_tags_per_session.delay(session_id)
    return {"message": "AI product tags creation task queued."}


@router.get(
    "/purchased-items",
    dependencies=[Depends(get_current_admin)],
    response_model=list[PurchasedItemOut],
)
async def get_purchased_items(
    limit: int = 100,
    offset: int = 0,
    item_type: str = None,
    email: str = None,
    user_id: int = None,
):
    query = PurchasedItem.all().limit(limit).offset(offset)
    if email:
        query = query.filter(email=email)
    if user_id:
        query = query.filter(user_id=user_id)
    if item_type:
        query = query.filter(item_type=item_type)
    return await PurchasedItemOut.from_queryset(query)
