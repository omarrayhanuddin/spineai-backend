from fastapi import APIRouter, Depends
from app.api.dependency import get_current_admin
from app.tasks.chat import (
    send_recommendations_notification,
    create_treatment_plan_from_ai_response,
    send_daily_treatment_notification,
    async_db_operation_for_treatment_notify,
    async_db_operation_for_recommendations_notify,
    async_db_operation_for_treatment_plan,
)

router = APIRouter(prefix="/v1/admin", tags=["Admin Endpoints"])


# test send recommendations notification
@router.post("/send-recommendations-notification")
async def send_recommendations_notification_endpoint(
    current_admin: dict = Depends(get_current_admin),
    function_only:bool=False
):
    if function_only:
        await async_db_operation_for_recommendations_notify()
        return {"message": "Function only."}
    send_recommendations_notification.delay()
    return {"message": "Recommendations notification task queued."}


# test create treatment plan from ai response
@router.post("/create-treatment-plan-from-ai-response")
async def create_treatment_plan_from_ai_response_endpoint(
    current_admin: dict = Depends(get_current_admin),
    function_only:bool=False
):
    if function_only:
        await async_db_operation_for_treatment_plan()
        return {"message": "Function only."}
    create_treatment_plan_from_ai_response.delay()
    return {"message": "Treatment plan creation task queued."}


# test send daily treatment notification
@router.post("/send-daily-treatment-notification")
async def send_daily_treatment_notification_endpoint(
    current_admin: dict = Depends(get_current_admin),
    function_only:bool=False
):
    print("1")
    if function_only:
        print("2")
        await async_db_operation_for_treatment_notify()
        return {"message": "Daily treatment notification task queued."}
    print("3")
    send_daily_treatment_notification.delay()
    return {"message": "Daily treatment notification task queued."}
