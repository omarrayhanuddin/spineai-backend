from fastapi import APIRouter, HTTPException
from app.models.coupon import Coupon
from app.schemas.coupon import CouponApply, CouponOut

router = APIRouter(prefix="/v1/coupon", tags=["Coupon Endpoints"])

@router.post("/apply", response_model=CouponOut)
async def apply_coupon(data: CouponApply):
    coupon = await Coupon.get_or_none(code=data.code)
    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")
    if not coupon.is_valid():
        raise HTTPException(status_code=400, detail="Coupon expired")
    return await CouponOut.from_tortoise_orm(coupon)
