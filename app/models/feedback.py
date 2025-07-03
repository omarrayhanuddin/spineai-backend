from tortoise import fields
from app.models.base import BaseModelWithoutID


class FeedBack(BaseModelWithoutID):
    full_name = fields.CharField(max_length=255, null=True)
    email = fields.CharField(max_length=255, null=True)
    feedback_type = fields.CharField(max_length=100)
    exp_rate = fields.SmallIntField(default=1)
    subjet = fields.CharField(max_length=255)
    details = fields.TextField()
    is_contact_us = fields.BooleanField(default=False)

    class Meta:
        table = "feedbacks"
