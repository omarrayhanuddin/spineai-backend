from fastapi import APIRouter, Depends, HTTPException
from app.api.dependency import get_current_user
from app.models.treatment_plan import TreatmentCategory, WeeklyPlan, Task
from app.schemas.treatment_plan import TreatmentCategoryOut, WeeklyPlanOut, TaskOut
from datetime import date

router = APIRouter(prefix="/v1/treatment-plan", tags=["Treatment Plan Endpoints"])


@router.get("/category/all")
async def get_all_treatment_categories(
    user=Depends(get_current_user), session_id: str = None
):
    if session_id:
        return {
            "categories": await TreatmentCategory.filter(
                session__id=session_id, session__user=user
            )
        }
    return {"categories": await TreatmentCategory.filter(session__user=user)}


@router.get("/category/{category_id}/weekly-plans", response_model=list[WeeklyPlanOut])
async def get_weekly_plans_for_category(
    category_id: int, user=Depends(get_current_user), filter_date: date = None
):
    category = await TreatmentCategory.get_or_none(id=category_id, session__user=user)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if filter_date:
        weekly_plans = (
            WeeklyPlan.filter(category=category, tasks__date=filter_date)
            .prefetch_related("tasks")
            .order_by("tasks__id")
        )
    else:
        weekly_plans = (
            WeeklyPlan.filter(category=category)
            .prefetch_related("tasks")
            .order_by("tasks__id")
        )
    return await WeeklyPlanOut.from_queryset(weekly_plans)


@router.get("/weekly-plan/{weekly_plan_id}/tasks", response_model=list[TaskOut])
async def get_tasks_for_weekly_plan(
    weekly_plan_id: int, user=Depends(get_current_user)
):
    weekly_plan = await WeeklyPlan.get_or_none(
        id=weekly_plan_id, category__session__user=user
    )
    if not weekly_plan:
        raise HTTPException(status_code=404, detail="Weekly plan not found")
    tasks = await Task.filter(weekly_plan=weekly_plan)
    return tasks
