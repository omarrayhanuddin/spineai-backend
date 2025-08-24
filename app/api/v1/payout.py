from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.models.user import User
from app.models.payout import WithdrawalRequest
from app.api.dependency import get_current_user, get_stripe_client
from stripe import StripeClient
from decimal import Decimal
from app.core.config import settings
router = APIRouter(tags=["Payout"], prefix="/payout")


class WithdrawalRequestIn(BaseModel):
    amount: float


@router.post("/onboard")
async def create_stripe_onboarding(
    user: User = Depends(get_current_user),
    stripe_client: StripeClient = Depends(get_stripe_client),
    refresh_url: str = settings.STRIPE_CANCEL_URL,
    sucess_url: str = settings.STRIPE_SUCCESS_URL,
    country: str = "US",
):
    """
    Create or fetch Stripe Express account onboarding link.
    User must complete this to add bank/card details.
    """

    if not user.stripe_connect_id:
        account = await stripe_client.accounts.create_async(
            {
                "type": "express",
                "country": country,
                "email": user.email,
            }
        )
        user.stripe_connect_id = account.id
        await user.save()

    account_link = await stripe_client.account_links.create_async(
        {
            "account": user.stripe_connect_id,
            "refresh_url": refresh_url,
            "return_url": sucess_url,
            "type": "account_onboarding",
        }
    )
    return {"onboarding_url": account_link.url}


@router.post("/withdraw")
async def withdraw_referral_bonus(
    payload: WithdrawalRequestIn,
    user: User = Depends(get_current_user),
    stripe_client: StripeClient= Depends(get_stripe_client),
):
    """
    Let a user withdraw referral bonus to their bank/card via Stripe Connect.
    """
    if payload.amount <= 0:
        raise HTTPException(400, "Invalid withdrawal amount")

    if user.referral_balance < payload.amount:
        raise HTTPException(400, "Insufficient referral balance")

    if not user.stripe_connect_id:
        raise HTTPException(400, "User has not completed payout onboarding")

    # Deduct balance in DB first
    user.referral_balance -= Decimal(payload.amount)
    await user.save()

    withdrawal = await WithdrawalRequest.create(
        user=user, amount=payload.amount, status="pending"
    )

    try:
        # Transfer funds from platform to connected account
        transfer = await stripe_client.transfers.create_async(
            {
                "amount": int(payload.amount * 100),
                "currency": "usd",
                "destination": user.stripe_connect_id,
            }
        )
        withdrawal.status = "paid"
        await withdrawal.save()
        return {"status": "success", "transfer_id": transfer.id}

    except Exception as e:
        withdrawal.status = "failed"
        await withdrawal.save()
        raise HTTPException(400, f"Payout failed: {str(e)}")