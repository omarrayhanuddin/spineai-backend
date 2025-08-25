from fastapi import APIRouter, Depends, HTTPException
from app.models.user import User
from app.models.payout import WithdrawalRequest, WithdrawMethodInfo
from app.schemas.payout import (
    WithdrawalRequestOut,
    WithdrawMethodInfoOut,
    WithdrawalRequestIn,
    WithdrawMethodInfoIn,
    WithdrawalRequestStatusUpdate,
)
from decimal import Decimal
from app.api.dependency import get_current_user, get_current_admin

router = APIRouter(tags=["Affiliate"], prefix="/affiliate")


@router.get("/dashboard")
async def get_affiliate_dashboard(
    user: User = Depends(get_current_user), q_user_id: int | None = None
):
    if q_user_id and user.is_admin:
        user = await User.get_or_none(id=q_user_id)
        if not user:
            raise HTTPException(
                status_code=404, detail="User with given ID does not exist."
            )

    return {
        "total_referrals": await User.filter(refferred_by=user.affiliate_id).count(),
        "total_paid_referrals": await User.filter(
            refferred_by=user.affiliate_id, referrer_bonus_applied=True
        ).count(),
        "affiliate_id": user.affiliate_id,
        "refferred_by": user.refferred_by,
        "referrer_bonus_applied": user.referrer_bonus_applied,
        "referral_balance": float(user.referral_balance),
        "has_withdraw_method": await user.withdraw_methods.all().count() > 0,
    }


@router.get("/withdrawals")
async def get_withdrawal_requests(
    user: User = Depends(get_current_user),
    limit: int = 10,
    offset: int = 0,
    status: str | None = None,
    q_user_id: int | None = None,
):
    """
    Get all withdrawal requests made by the user.
    """
    query = WithdrawalRequest.all()
    if q_user_id and user.is_admin:
        query = query.filter(user_id=q_user_id)
    elif q_user_id is None and user.is_admin:
        pass
    else:
        query = query.filter(user_id=user.id)
    if status:
        query = query.filter(status=status)
    withdrawals = await query.order_by("-created_at").limit(limit).offset(offset)
    total_count = await query.count()
    return {"total_count": total_count, "withdrawals": withdrawals}


@router.get("/all-referal-users")
async def get_all_referal_users(
    user: User = Depends(get_current_user),
    limit: int = 10,
    offset: int = 0,
    q_user_id: int | None = None,
    paid_only: bool | None = None,
):
    """
    Get all users referred by the user.
    """
    if q_user_id and user.is_admin:
        user = await User.get_or_none(id=q_user_id)
        if not user:
            raise HTTPException(
                status_code=404, detail="User with given ID does not exist."
            )
    filters = {"refferred_by": user.affiliate_id}
    if paid_only is not None:
        filters["referrer_bonus_applied"] = paid_only

    referal_users = await User.filter(**filters).limit(limit).offset(offset)
    total_count = await User.filter(**filters).count()
    return {"total_count": total_count, "referal_users": referal_users}


@router.get("/all-withdrawmethods")
async def get_all_withdraw_methods(
    user: User = Depends(get_current_user),
    limit: int = 10,
    offset: int = 0,
    q_user_id: int | None = None,
):
    """
    Get all withdraw methods added by the user.
    """
    if q_user_id and user.is_admin:
        user = await User.get_or_none(id=q_user_id)
        if not user:
            raise HTTPException(
                status_code=404, detail="User with given ID does not exist."
            )

    withdraw_methods = await user.withdraw_methods.all().limit(limit).offset(offset)
    total_count = await user.withdraw_methods.all().count()
    return {"total_count": total_count, "withdraw_methods": withdraw_methods}


@router.post("/create-withdrawmethod")
async def create_withdraw_method(
    payload: WithdrawMethodInfoIn,
    user: User = Depends(get_current_user),
):
    """
    Let a user create a withdraw method.
    """
    withdraw_method = await WithdrawMethodInfo.create(
        user=user, method_type=payload.method_type, details=payload.details
    )
    return withdraw_method


@router.post("/create-withdrawal-request")
async def create_withdrawal_request(
    payload: WithdrawalRequestIn,
    user: User = Depends(get_current_user),
):
    """
    Let a user create a withdrawal request to withdraw referral bonus.
    """
    if payload.amount <= 0:
        raise HTTPException(400, "Invalid withdrawal amount")

    if user.referral_balance < payload.amount:
        raise HTTPException(400, "Insufficient referral balance")

    withdraw_method = await WithdrawMethodInfo.get_or_none(
        id=payload.withdraw_method_id
    )
    if not withdraw_method or withdraw_method.user_id != user.id:
        raise HTTPException(400, "Invalid withdraw method")

    # Deduct balance in DB first
    user.referral_balance -= Decimal(payload.amount)
    await user.save()

    withdrawal = await WithdrawalRequest.create(
        user=user,
        amount=payload.amount,
        status="pending",
        withdraw_method=withdraw_method,
    )
    return withdrawal


@router.get("/withdrawals/{withdrawal_id}")
async def get_withdrawal_request_details(
    withdrawal_id: str,
    user: User = Depends(get_current_user),
):
    """
    Get details of a specific withdrawal request by ID.
    """
    withdrawal = await WithdrawalRequest.get_or_none(id=withdrawal_id).prefetch_related(
        "user", "withdraw_method"
    )
    if not withdrawal:
        raise HTTPException(404, "Withdrawal request not found")

    if withdrawal.user_id != user.id and not user.is_admin:
        raise HTTPException(403, "Not authorized to view this withdrawal request")

    return withdrawal


@router.post("/admin/update-withdrawal-status/{withdrawal_id}")
async def admin_update_withdrawal_status(
    withdrawal_id: str,
    payload: WithdrawalRequestStatusUpdate,
    admin: User = Depends(get_current_admin),
):
    """
    Let an admin update the status of a withdrawal request.
    """
    new_status = payload.new_status
    rejection_reason = payload.rejection_reason
    if new_status not in ("pending", "approved", "rejected", "paid"):
        raise HTTPException(400, "Invalid status")

    withdrawal = await WithdrawalRequest.get_or_none(id=withdrawal_id).prefetch_related(
        "user"
    )
    if not withdrawal:
        raise HTTPException(404, "Withdrawal request not found")

    if withdrawal.status == "rejected" and new_status != "rejected":
        # If previously rejected, and now changing to non-rejected status, no balance change
        pass
    elif withdrawal.status != "rejected" and new_status == "rejected":
        # If changing to rejected, refund the amount back to user's referral balance
        user = withdrawal.user
        user.referral_balance += withdrawal.amount
        await user.save()

    withdrawal.status = new_status
    if new_status == "rejected":
        withdrawal.rejection_reason = rejection_reason
    await withdrawal.save()
    return {
        "message": f"Withdrawal request status updated to {new_status}",
        "withdrawal": withdrawal,
    }
