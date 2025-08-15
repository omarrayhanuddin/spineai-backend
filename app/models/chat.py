from tortoise import fields
from app.models.base import BaseModelWithoutID
from app.core.config import settings
from tortoise_vector.field import VectorField


class ChatSession(BaseModelWithoutID):
    id = fields.UUIDField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="chat_sessions")
    title = fields.TextField(null=True)
    findings = fields.JSONField(null=True)
    image_summary = fields.JSONField(null=True)
    detected_region = fields.CharField(max_length=255, null=True)
    recommendations = fields.JSONField(null=True)
    suggested_product_tags = fields.JSONField(null=True)
    recommendations_notified_at = fields.DatetimeField(null=True)
    is_diagnosed = fields.BooleanField(default=False)

    class Meta:
        table = "sessions"


class ChatMessage(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    session = fields.ForeignKeyField("models.ChatSession", related_name="chat_messages")
    sender = fields.CharField(max_length=10)
    content = fields.TextField(null=True)
    embedding = VectorField(vector_size=settings.EMBEDDING_DIMENSIONS, null=True)
    is_relevant = fields.BooleanField(default=True)

    class Meta:
        table = "messages"


class GeneratedReport(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    title = fields.TextField(null=True)
    session = fields.ForeignKeyField(
        "models.ChatSession", related_name="generated_reports"
    )
    user = fields.ForeignKeyField("models.User", related_name="generated_reports")
    content = fields.TextField()
    message_id = fields.CharField(max_length=255)

    class Meta:
        table = "ai_generated_reports"


class ChatImage(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    message = fields.ForeignKeyField("models.ChatMessage", related_name="chat_images")
    img_base64 = fields.TextField()
    file_type = fields.CharField(max_length=10, null=True)
    meta_data = fields.JSONField(null=True)
    filename = fields.TextField(null=True)
    s3_url = fields.TextField()
    is_relevant = fields.BooleanField(default=True)

    class Meta:
        table = "images"

    class PydanticMeta:
        exclude = ("img_base64",)


class UserUploadedFile(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    message = fields.ForeignKeyField(
        "models.ChatMessage",
        related_name="user_uploaded_files",
        on_delete=fields.SET_NULL,
        null=True,
    )
    user = fields.ForeignKeyField("models.User", related_name="uploaded_files")
    file_name = fields.CharField(max_length=255)
    file_type = fields.CharField(max_length=10)
    file_size = fields.IntField()
    file_url = fields.TextField()

    class Meta:
        table = "uploaded_files"

    class PydanticMeta:
        exclude = ("user", "message")


class Usage(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    usage_type = fields.CharField(max_length=10)
    user = fields.ForeignKeyField("models.User", related_name="usage")
    usage_count = fields.IntField(default=1)
    source = fields.CharField(max_length=100)

    class Meta:
        table = "usages"
