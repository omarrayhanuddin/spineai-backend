import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from app.models.user import User
from app.core.config import settings
from fastapi import Request
from httpx import AsyncClient
from mistralai import Mistral
from openai import AsyncClient as OpenAiAsyncClient
from stripe import StripeClient


async def get_httpx_client(request: Request) -> AsyncClient:
    return request.app.state.httpx_client


async def get_mistral_client(request: Request) -> Mistral:
    return request.app.state.mistral_client


async def get_openai_client(request: Request) -> OpenAiAsyncClient:
    return request.app.state.openai_client


async def get_stripe_client(request: Request) -> StripeClient:
    return request.app.state.stripe_client


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        secret_key: str = payload.get("secret_key")
        if user_id is None or secret_key is None:
            raise HTTPException(
                status_code=401, detail="Invalid authentication credentials"
            )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401, detail="Invalid authentication credentials"
        )
    user = await User.get_or_none(pk=user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.secret_key != secret_key:
        raise HTTPException(
            status_code=401, detail="Invalid secret key - possible session invalidation"
        )
    return await User.get(pk=user_id)


async def get_current_admin(user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized as admin")
    return user


async def check_subscription_active(user: User = Depends(get_current_user)):
    if user.subscription_status == "past_due":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Your payment failed. Please update your billing information.",
        )
    elif user.subscription_status not in {"active", "free"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Subscription is not active (status: {user.subscription_status})",
        )
    return user
