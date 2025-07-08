from tortoise import fields
from app.core.config import settings
from app.models.base import BaseModelWithoutID
from tortoise_vector.field import VectorField


class ChatSession(BaseModelWithoutID):
    id = fields.UUIDField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="chat_sessions")
    title = fields.TextField(null=True)
    findings = fields.JSONField(null=True)
    recommendations = fields.JSONField(null=True)
    is_diagnosed = fields.BooleanField(default=False)


    class Meta:
        table = "sessions"

    def __str__(self):
        return self.user.email


class ChatMessage(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    session = fields.ForeignKeyField("models.ChatSession", related_name="chat_messages")
    sender = fields.CharField(max_length=10)
    content = fields.TextField(null=True)
    embedding = VectorField(vector_size=settings.EMBEDDING_DIMENSIONS)
    is_relevant = fields.BooleanField(default=True) 

    class Meta:
        table = "messages"


class ChatImage(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    message = fields.ForeignKeyField("models.ChatMessage", related_name="chat_images")
    img_base64 = fields.TextField()
    s3_url = fields.TextField()
    is_relevant = fields.BooleanField(default=True)

    class Meta:
        table = "images"

    class PydanticMeta:
        exclude = ("img_base64",)

class Usage(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="page_usages")
    usage_count = fields.IntField(default=1)
    source = fields.CharField(max_length=100)
    is_message = fields.BooleanField(default=False)

    class Meta:
        table = "usages"
