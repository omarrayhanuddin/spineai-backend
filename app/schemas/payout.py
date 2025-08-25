from app.models.payout import WithdrawMethodInfo, WithdrawalRequest
from tortoise.contrib.pydantic.creator import pydantic_model_creator
from pydantic import BaseModel

WithdrawMethodInfoOut = pydantic_model_creator(
    WithdrawMethodInfo,
    include=["id", "method_type", "details", "created_at"],
)
WithdrawalRequestOut = pydantic_model_creator(
    WithdrawalRequest,
    include=["id", "amount", "status", "created_at", "withdraw_method", "rejection_reason"],
)

class WithdrawalRequestIn(BaseModel):
    amount: float
    withdraw_method_id: str

class WithdrawMethodInfoIn(BaseModel):
    method_type: str
    details: dict

class WithdrawalRequestStatusUpdate(BaseModel):
    new_status: str
    rejection_reason: str | None = None