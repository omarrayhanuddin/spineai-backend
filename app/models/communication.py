from tortoise import fields
from app.models.base import BaseModelWithoutID


class Communication(BaseModelWithoutID):
    full_name = fields.CharField(max_length=255)
    email = fields.CharField(max_length=255)
    subject = fields.CharField(max_length=255)
    details = fields.TextField()
    is_contact_us = fields.BooleanField(default=False)

    class Meta:
        table = "feedbacks"

