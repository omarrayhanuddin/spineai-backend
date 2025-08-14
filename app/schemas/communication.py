from tortoise.contrib.pydantic import pydantic_model_creator
from app.models.communication import Communication


class CommunicationIn(
    pydantic_model_creator(
        Communication,
        include=[
            "full_name",
            "email",
            "subject",
            "details",
            "is_contact_us"
        ],
    )
):
    pass


CommunicationOut = pydantic_model_creator(
    Communication,
    include=[
        "id",
        "full_name",
        "email",
        "subject",
        "details",
    ],
)
