from tortoise import fields
from app.models.base import BaseModelWithoutID


class Notification(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="notifications")
    session = fields.ForeignKeyField("models.ChatSession", related_name="notifications")
    message = fields.TextField()
    type = fields.CharField(max_length=50)
    is_read = fields.BooleanField(default=False)

    class Meta:
        table = "notifications"
    