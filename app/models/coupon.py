from app.models.base import BaseModelWithoutID
from tortoise import fields

class Coupon(BaseModelWithoutID):
    code = fields.CharField(max_length=50, unique=True)
    discount_type = fields.CharField(max_length=10)  
    discount_value = fields.DecimalField(max_digits=10, decimal_places=2)
    expires_at = fields.DatetimeField(null=True)

    class Meta:
        table = "coupons"
        ordering = ["-created_at"]

    def is_valid(self):
        from datetime import datetime
        return not self.expires_at or self.expires_at > datetime.utcnow()
