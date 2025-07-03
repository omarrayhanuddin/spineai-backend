from tortoise import fields
from app.core.config import settings
from app.models.base import BaseModelWithoutID
from tortoise_vector.field import VectorField


class ChatSession(BaseModelWithoutID):
    id = fields.UUIDField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="chat_sessions")
    title = fields.TextField(null=True)

    class Meta:
        table = "chat_sessions"

    def __str__(self):
        return self.user.email


class Message(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    session = fields.ForeignKeyField("models.ChatSession", related_name="messages")
    sender = fields.CharField(max_length=10)
    content = fields.TextField()
    created_at = fields.DatetimeField(auto_now_add=True)
    initial = fields.BooleanField(default=False)
    # input_tokens = fields.IntField(null=True, default=0)
    # output_tokens = fields.IntField(null=True, default=0)
    # total_tokens = fields.IntField(null=True, default=0)

    class Meta:
        table = "messages"


class ChatDocument(BaseModelWithoutID):
    id = fields.UUIDField(primary_key=True)
    chat = fields.ForeignKeyField("models.ChatSession", related_name="chat_documents")
    full_text = fields.TextField()
    document_url = fields.TextField()
    name = fields.CharField(max_length=255)
    size = fields.IntField()
    extracted_page_count = fields.IntField(default=0)

    class Meta:
        table = "chat_documents"


class DocumentChunk(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    document = fields.ForeignKeyField("models.ChatDocument", related_name="chunks")
    content = fields.TextField()
    embedding = VectorField(vector_size=settings.OPENAI_VECTOR_SIZE)

    class Meta:
        table = "document_chat_chunks"


class Usage(BaseModelWithoutID):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField("models.User", related_name="page_usages")
    usage_count = fields.IntField(default=1)
    source = fields.CharField(max_length=100)
    is_message = fields.BooleanField(default=False)

    class Meta:
        table = "usages"
