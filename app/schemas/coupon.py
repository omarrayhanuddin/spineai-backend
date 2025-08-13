from tortoise.contrib.pydantic.creator import pydantic_model_creator
from app.models.coupon import Coupon
from pydantic import BaseModel
from datetime import datetime

CouponOut = pydantic_model_creator(
    Coupon, include=["id", "code", "discount_type", "discount_value", "expires_at"]
)
CouponIn = pydantic_model_creator(
    Coupon, exclude=["id", "created_at", "updated_at"]
)

class CouponApply(BaseModel):
    code: str
