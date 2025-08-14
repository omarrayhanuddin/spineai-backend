from app.models.base import BaseModelWithoutID
from tortoise import fields

class Tag(BaseModelWithoutID):
    name = fields.CharField(max_length=50, unique=True)

    class Meta:
        table = "tags"
        ordering = ["name"]


class Product(BaseModelWithoutID):
    name = fields.CharField(max_length=255)
    description = fields.TextField(null=True)
    shopify_url = fields.TextField(null=True)
    tags = fields.ManyToManyField("models.Tag", related_name="products")

    class Meta:
        table = "products"
        ordering = ["-created_at"]