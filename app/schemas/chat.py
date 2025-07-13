from pydantic import BaseModel
from app.models.chat import ChatSession, ChatMessage, ChatImage, GeneratedReport, UserUploadedFile
from tortoise.contrib.pydantic.creator import pydantic_model_creator
from tortoise import Tortoise


Tortoise.init_models(
    [
        "app.models.user",
        "app.models.chat",
        # "app.models.payment",
    ],
    "models",
)


ChatSessionOut = pydantic_model_creator(
    ChatSession, include=["id", "title", "created_at", "is_diagnosed"]
)
MessageOut = pydantic_model_creator(
    ChatMessage,
    include=["id", "sender", "content", "created_at", "updated_at", "chat_images"],
    name="MessageOut",
)
ImageOut = pydantic_model_creator(
    ChatImage,
    include=["id", "s3_url", "is_relevant", "filename"],
    name="ImageOut",
)

GeneratedReportOut = pydantic_model_creator(
    GeneratedReport,
    include=["id", "title", "message_id", "created_at"],
    name="GeneratedReportOut",
)

UserUploadedFileOut = pydantic_model_creator(
    UserUploadedFile,
    include=["id", "file_name", "file_type", "file_size", "file_url" ,"created_at"],
    name="UserUploadedFileOut",
)


class ChatMessageIn(BaseModel):
    prompt: str


class RenameSession(BaseModel):
    title: str
