from app.models.notification import Notification
from tortoise.contrib.pydantic.creator import pydantic_model_creator
from tortoise import Tortoise
from pydantic import BaseModel

Tortoise.init_models(
    [
        "app.models.user",
        "app.models.chat",
        "app.models.payment",
        "app.models.notification",
    ],
    "models",
)

NotificationOut = pydantic_model_creator(
    Notification, 
    include=["id", "message", "created_at", "type", "is_read", "session_id"],
    name="NotificationOut",
)


class NotifcationUpdate(BaseModel):
    ids: list[str]