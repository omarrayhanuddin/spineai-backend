from tortoise.contrib.pydantic import pydantic_model_creator
from app.models.treatment_plan import TreatmentCategory, WeeklyPlan, Task

TreatmentCategoryOut = pydantic_model_creator(
    TreatmentCategory, name="TreatmentCategoryOut"
)

WeeklyPlanOut = pydantic_model_creator(
    WeeklyPlan,
    name="WeeklyPlanOut",
    include=("id", "name", "description", "start_date", "end_date", "tasks"),
)
TaskOut = pydantic_model_creator(
    Task, name="TaskOut", include=("id", "title", "description", "status", "date")
)
