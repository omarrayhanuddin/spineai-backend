from pydantic import BaseModel, EmailStr
from app.models.user import User
from tortoise.contrib.pydantic.creator import pydantic_model_creator


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    agreed_to_toc: bool


UserOut = pydantic_model_creator(
    User,
    include=[
        "id",
        "full_name",
        "email",
        "is_admin",
        "subscription_status",
        "subscription_id",
        "current_plan",
        "next_billing_date",
        "has_valid_card",
    ],
    # exclude=["chat_sessions"]
)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ChangePassword(BaseModel):
    old_password: str
    new_password: str


class ForgotPassword(BaseModel):
    email: EmailStr


class ResetPassword(BaseModel):
    token: str
    new_password: str


class UpdateProfile(BaseModel):
    full_name: str
