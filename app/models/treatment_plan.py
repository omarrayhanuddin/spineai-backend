from tortoise import fields, models
from app.models.base import BaseModelWithoutID


class TreatmentCategory(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, description="e.g., 'exercise', 'cold therapy'")
    session = fields.ForeignKeyField("models.ChatSession", related_name="treatment_plans")

    class Meta:
        table = "treatment_categories"

    def __str__(self):
        return self.name

class WeeklyPlan(models.Model):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=255, description="e.g., 'Week-1'")
    description = fields.TextField()
    start_date = fields.DateField()
    end_date = fields.DateField()
    category: fields.ForeignKeyRelation[TreatmentCategory] = fields.ForeignKeyField(
        "models.TreatmentCategory", related_name="weekly_plans"
    )

    class Meta:
        table = "weekly_plans"

    def __str__(self):
        return f"{self.category.name} - {self.name}"

class Task(models.Model):
    id = fields.IntField(pk=True)
    title = fields.CharField(max_length=255)
    description = fields.TextField()
    date = fields.DateField()
    status = fields.CharField(max_length=50, default="pending", description="e.g., 'completed', 'pending', 'in progress'")
    weekly_plan: fields.ForeignKeyRelation[WeeklyPlan] = fields.ForeignKeyField(
        "models.WeeklyPlan", related_name="tasks"
    )

    class Meta:
        table = "tasks"

    def __str__(self):
        return f"{self.title} ({self.status}) for {self.weekly_plan.name}"

