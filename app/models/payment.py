from tortoise import fields
from app.models.base import BaseModelWithoutID


class Plan(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50, unique=True)
    description = fields.TextField(null=True)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    stripe_price_id = fields.CharField(max_length=255, unique=True)

    class Meta:
        table = "plans"

    def __str__(self):
        return self.name


class PendingEvent(BaseModelWithoutID):
    id = fields.CharField(max_length=255, pk=True)
    type = fields.CharField(max_length=255)
    created = fields.DatetimeField()
    payload = fields.JSONField()
    processed = fields.BooleanField(default=False)

    class Meta:
        table = "pending_stripe_events"
