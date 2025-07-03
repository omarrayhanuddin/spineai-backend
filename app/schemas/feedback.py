from tortoise.contrib.pydantic import pydantic_model_creator
from app.models.feedback import FeedBack


class FeedBackIn(
    pydantic_model_creator(
        FeedBack,
        include=[
            "feedback_type",
            "exp_rate",
            "subjet",
            "details",
        ],
    )
):
    pass


FeedBackOut = pydantic_model_creator(
    FeedBack,
    include=[
        "id",
        "full_name",
        "email",
        "feedback_type",
        "exp_rate",
        "subjet",
        "details",
    ],
)


class ContactUsIn(
    pydantic_model_creator(
        FeedBack,
        include=[
            "full_name",
            "email",
            "feedback_type",
            "subjet",
            "details",
        ],
    )
):
    pass


class ContactUsOut(
    pydantic_model_creator(
        FeedBack,
        include=[
            "id",
            "full_name",
            "email",
            "feedback_type",
            "subjet",
            "details",
        ],
    )
):
    pass
