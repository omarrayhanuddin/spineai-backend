from pydantic import BaseModel
from app.models.chat import ChatDocument, ChatSession, Message
from tortoise.contrib.pydantic.creator import pydantic_model_creator
from tortoise import Tortoise

Tortoise.init_models(
    [
        "app.models.user",
        "app.models.chat",
        "app.models.payment",
    ],
    "models",
)

ChatDocumentOut = pydantic_model_creator(
    ChatDocument,
    include=["id", "name", "size", "chat_id", "extracted_page_count"],
)
ChatSessionOut = pydantic_model_creator(
    ChatSession, include=["id", "title", "created_at"]
)
MessageOut = pydantic_model_creator(
    Message, include=["id", "sender", "content", "created_at", "updated_at"]
)


class ChatMessageIn(BaseModel):
    prompt: str


class RenameSession(BaseModel):
    title: str
