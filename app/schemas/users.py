from pydantic import BaseModel, EmailStr
from app.models.user import User
from tortoise.contrib.pydantic.creator import pydantic_model_creator


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    agreed_to_toc: bool
    refferred_by: str = None


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
        "allow_email_notifications",
        "allow_push_notifications",
        "affiliate_id",
        "refferred_by",
        "referrer_bonus_applied",
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


class UserSettings(BaseModel):
    allow_email_notifications: bool
    allow_push_notifications: bool