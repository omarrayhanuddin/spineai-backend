from tortoise import fields
from app.models.base import BaseModelWithoutID


class Plan(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    name = fields.CharField(max_length=50, unique=True)
    description = fields.TextField(null=True)
    price = fields.DecimalField(max_digits=10, decimal_places=2)
    stripe_price_id = fields.CharField(max_length=255, unique=True)
    chat_model = fields.CharField(max_length=20, null=True)
    message_limit = fields.IntField(default=20)
    image_limit = fields.IntField(default=2)
    file_limit = fields.IntField(default=1)
    weekly_reminder = fields.BooleanField(default=False)
    treatment_plan = fields.BooleanField(default=False)
    comission_percentage = fields.IntField(default=0)

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


class PurchasedItem(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="purchased_items",
        on_delete=fields.SET_NULL,
        null=True,
    )
    email = fields.CharField(max_length=255, null=True)
    item_type = fields.CharField(max_length=50)
    quantity = fields.IntField(default=1)
    purchase_date = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "purchased_items"
