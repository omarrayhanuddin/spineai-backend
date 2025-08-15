from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from app.schemas.users import (
    UserCreate,
    UserOut,
    UserLogin,
    Token,
    ResetPassword,
    ForgotPassword,
    ChangePassword,
    UpdateProfile,
    UserSettings,
)
from app.services.email_service import send_email
from app.models.user import User
from app.utils.helpers import (
    verify_password,
    create_access_token,
    get_password_hash,
    generate_token,
    generate_secret_key,
)
from app.api.dependency import get_current_user, get_stripe_client, get_current_admin
from app.core.config import settings
from stripe import StripeClient
from app.models.payment import Plan

router = APIRouter(prefix="/v1/auth", tags=["User Endpoints"])


@router.post("/register", response_model=UserOut)
async def register(user: UserCreate, background_tasks: BackgroundTasks):
    if await User.filter(email=user.email).exists():
        raise HTTPException(400, "Email already registered")
    user = await User.create(**user.model_dump(exclude_unset=True))
    context = {
        "user_name": user.full_name,
        "verification_link": f"{settings.SITE_DOMIN}/auth/verify-email?token={user.verification_token}",
    }

    background_tasks.add_task(
        send_email,
        subject="Action Required: Verify Your Email on SpineAi",
        recipient=user.email,
        template_name="email_verify.html",
        context=context,
    )
    return user


@router.post("/resend-verification-email")
async def resend_verification_email(
    form: ForgotPassword, background_tasks: BackgroundTasks
):
    user = await User.get_or_none(email=form.email)
    if user is None:
        raise HTTPException(400, "User with this email does not exists")
    if user.is_verified:
        raise HTTPException(400, "User Already verified")

    context = {
        "user_name": user.full_name,
        "verification_link": f"{settings.SITE_DOMIN}/auth/verify-email?token={user.verification_token}",
    }

    background_tasks.add_task(
        send_email,
        subject="Action Required: Verify Your Email on SpineAi",
        recipient=user.email,
        template_name="email_verify.html",
        context=context,
    )
    return {"message": "If the email is registered, a verification link will be sent."}


@router.get("/verify-email/")
async def verify_email(
    token: str, stripe_client: StripeClient = Depends(get_stripe_client)
):
    user = await User.get_or_none(verification_token=token)
    if user is None:
        raise HTTPException(400, "Invalid token")
    user.verification_token = None
    if user.stripe_customer_id is None or user.stripe_customer_id.strip() == "":
        customer = await stripe_client.customers.create_async(
            {"name": user.full_name, "email": user.email}
        )
        user.stripe_customer_id = customer.id
    # await user.save()
    # plan = await Plan.get_or_none(name__iexact="free")
    # user.subscription_status = "active"
    # user.current_plan = plan.stripe_price_id
    await user.save()
    return {"message": "Email verified successfully"}


@router.post("/login", response_model=Token)
async def login(form: UserLogin):
    user = await User.get_or_none(email=form.email)
    if user is None:
        raise HTTPException(400, "User with this email does not exists")
    if not verify_password(form.password, user.password):
        raise HTTPException(401, "Invalid Password")
    if not user.is_verified:
        raise HTTPException(403, "Email not verified")
    if user.secret_key is None or user.secret_key == "":
        user.secret_key = generate_secret_key()
        await user.save()
    access_token = create_access_token(
        {"sub": str(user.id), "secret_key": user.secret_key}
    )
    return {"access_token": access_token}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.put("/change-password")
async def change_password(form: ChangePassword, user: User = Depends(get_current_user)):
    if not verify_password(form.old_password, user.password):
        raise HTTPException(400, "Old password incorrect")
    user.password = get_password_hash(form.new_password)
    user.secret_key = generate_secret_key()
    await user.save()
    access_token = create_access_token(
        {"sub": str(user.id), "secret_key": user.secret_key}
    )
    return {"access_token": access_token}


@router.post("/forgot-password")
async def forgot_password(form: ForgotPassword, background_tasks: BackgroundTasks):
    user = await User.get_or_none(email=form.email)
    if user is None:
        return {"message": "If the email is registered, a reset link will be sent."}
    token = generate_token()
    user.reset_token = token
    await user.save()
    context = {
        "user_name": user.full_name,
        "reset_link": f"{settings.SITE_DOMIN}/auth/reset-password?token={user.reset_token}",
    }

    background_tasks.add_task(
        send_email,
        subject="SpineAi Password Reset Request",
        recipient=user.email,
        template_name="reset_password.html",
        context=context,
    )
    return {"message": "Reset link sent"}


@router.post("/reset-password")
async def reset_password(form: ResetPassword):
    user = await User.get_or_none(reset_token=form.token)
    if user is None:
        raise HTTPException(400, "Invalid token")
    user.password = get_password_hash(form.new_password)
    user.reset_token = None
    user.secret_key = generate_secret_key()
    await user.save()
    return {"message": "Password reset successful"}


@router.put("/update-profile")
async def update_profile(data: UpdateProfile, user: User = Depends(get_current_user)):
    user.full_name = data.full_name
    await user.save()
    return {"message": "Profile updated"}


@router.get(
    "/users", dependencies=[Depends(get_current_admin)], response_model=list[UserOut]
)
async def users(offset: int = 0, limit: int = 10):
    return await User.all().limit(limit).offset(offset)


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)):
    user.secret_key = generate_secret_key()
    await user.save()
    return {"message": "Logout successfull"}


@router.put("/update-settings", response_model=UserOut)
async def update_user_settings(
    settings: UserSettings, user: User = Depends(get_current_user)
):
    user.update_from_dict(settings.model_dump())
    await user.save()
    await user.refresh_from_db()
    return user
