from pydantic import BaseModel
from app.models.chat import ChatSession, ChatMessage, ChatImage
from tortoise.contrib.pydantic.creator import pydantic_model_creator
from tortoise import Tortoise
from fastapi import UploadFile
from datetime import datetime
from typing import Optional, List

Tortoise.init_models(
    [
        "app.models.user",
        "app.models.chat",
        # "app.models.payment",
    ],
    "models",
)


ChatSessionOut = pydantic_model_creator(
    ChatSession, include=["id", "title", "created_at"]
)
MessageOut = pydantic_model_creator(
    ChatMessage,
    include=["id", "sender", "content", "created_at", "updated_at", "chat_images"],
    name="MessageOut",
)
ImageOut = pydantic_model_creator(
    ChatImage,
    include=["id", "s3_url", "is_relevant"],
    name="ImageOut",
)


class ChatMessageIn(BaseModel):
    prompt: str


class RenameSession(BaseModel):
    title: str


class UploadFileWIthLink(BaseModel):
    s3_url: str
    image: UploadFile | str


class ChatInput(BaseModel):
    message: str | None
    images: list[UploadFileWIthLink] = []
