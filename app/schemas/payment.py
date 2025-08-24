from tortoise.contrib.pydantic import pydantic_model_creator
from app.models.payment import Plan, PurchasedItem

from tortoise import Tortoise

Tortoise.init_models(
    [
        "app.models.user",
    ],
    "models",
)
PlanOut = pydantic_model_creator(
    Plan,
    include=[
        "id",
        "name",
        "description",
        "price",
        "page_limit",
        "stripe_price_id",
        "message_limit",
    ],
)

PlanInBase = pydantic_model_creator(
    Plan,
    include=["name", "description", "price", "stripe_price_id", "page_limit", "model"],
)


class PlanIn(PlanInBase):
    pass


PurchasedItemOut = pydantic_model_creator(
    PurchasedItem,
    include=["id", "user", "email", "item_type", "quantity", "purchase_date"],
)
