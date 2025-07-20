from app.core.config import settings
from tortoise.contrib.fastapi import register_tortoise
from fastapi import FastAPI

TORTOISE_ORM = {
    "connections": {"default": settings.DATABASE_URL},
    "apps": {
        "models": {
            "models": [
                "app.models.user",
                "app.models.chat",
                "app.models.payment",
                "app.models.notification",
                "app.models.treatment_plan",
                # "app.models.feedback",
                "aerich.models",
            ],
            "default_connection": "default",
        },
    },
}


def init_db(app: FastAPI) -> None:
    register_tortoise(
        app,
        config=TORTOISE_ORM,
        generate_schemas=True,
        add_exception_handlers=True,
    )
