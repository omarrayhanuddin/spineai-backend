from tortoise.contrib.pydantic.creator import pydantic_model_creator
from app.models.product import Product, Tag
from pydantic import BaseModel
from tortoise import Tortoise

Tortoise.init_models(
    [
        "app.models.product",
    ],
    "models",
)
ProductOut = pydantic_model_creator(
    Product, include=["id", "name", "description", "shopify_url", "tags__id"]
)
TagOut = pydantic_model_creator(Tag, include=["id", "name"], name="TagOut")
ProductIn = pydantic_model_creator(Product, exclude=["id", "created_at", "updated_at"])


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    shopify_url: str | None = None
    tags: list[int|str] | None = None


class TagIn(BaseModel):
    name: str
