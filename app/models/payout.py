from tortoise import fields
from app.models.base import BaseModelWithoutID

class WithdrawalRequest(BaseModelWithoutID):
    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="withdrawals")
    amount = fields.DecimalField(max_digits=10, decimal_places=2)
    status = fields.CharField(max_length=20, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "withdrawal_requests"
        ordering = ["-created_at"]
