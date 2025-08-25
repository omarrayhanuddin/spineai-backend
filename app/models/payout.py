from tortoise import fields
from app.models.base import BaseModelWithoutID


class WithdrawMethodInfo(BaseModelWithoutID):
    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="withdraw_methods")
    method_type = fields.CharField(max_length=50)
    details = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "withdraw_methods"
        ordering = ["-created_at"]


class WithdrawalRequest(BaseModelWithoutID):
    id = fields.UUIDField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="withdrawals")
    amount = fields.DecimalField(max_digits=10, decimal_places=2)
    status = fields.CharField(max_length=20, default="pending")
    created_at = fields.DatetimeField(auto_now_add=True)
    withdraw_method = fields.ForeignKeyField(
        "models.WithdrawMethodInfo", related_name="withdrawal_requests", null=True,
        on_delete=fields.SET_NULL
    )
    rejection_reason = fields.TextField(null=True)

    class Meta:
        table = "withdrawal_requests"
        ordering = ["-created_at"]
