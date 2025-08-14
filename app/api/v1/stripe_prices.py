from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from stripe import StripeClient
from app.core.config import settings
from typing import List, Optional
from pydantic import BaseModel
from app.api.dependency import get_stripe_client
router = APIRouter(prefix="/v1/stripe/prices", tags=["Stripe Price Management"])
security = HTTPBearer()

class PriceResponse(BaseModel):
    id: str
    active: bool
    currency: str
    unit_amount: int
    product: str
    type: str
    livemode: bool

class CreatePriceRequest(BaseModel):
    product_id: str
    unit_amount: int  # in cents (e.g., 1000 = $10.00)
    currency: str = "usd"

@router.get("/verify/{price_id}", response_model=PriceResponse)
async def verify_price(
    price_id: str,
    stripe_client: StripeClient = Depends(get_stripe_client)
):
    """Verify if a price exists in Stripe"""
    try:
        price = await stripe_client.prices.retrieve_async(price_id)
        return {
            "id": price.id,
            "active": price.active,
            "currency": price.currency,
            "unit_amount": price.unit_amount,
            "product": price.product,
            "type": price.type,
            "livemode": price.livemode
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Price verification failed: {str(e)}")

@router.get("/list", response_model=List[PriceResponse])
async def list_prices(
    active: Optional[bool] = True,
    limit: int = 10,
    stripe_client: StripeClient = Depends(get_stripe_client)
):
    """List all prices in Stripe"""
    try:
        prices = await stripe_client.prices.list_async(active=active, limit=limit)
        return [{
            "id": p.id,
            "active": p.active,
            "currency": p.currency,
            "unit_amount": p.unit_amount,
            "product": p.product,
            "type": p.type,
            "livemode": p.livemode
        } for p in prices.data]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to list prices: {str(e)}")

@router.post("/create", response_model=PriceResponse)
async def create_price(
    request: CreatePriceRequest,
    stripe_client: StripeClient = Depends(get_stripe_client)
):
    """Create a new price in Stripe"""
    try:
        price = await stripe_client.prices.create_async(
            product=request.product_id,
            unit_amount=request.unit_amount,
            currency=request.currency
        )
        return {
            "id": price.id,
            "active": price.active,
            "currency": price.currency,
            "unit_amount": price.unit_amount,
            "product": price.product,
            "type": price.type,
            "livemode": price.livemode
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Price creation failed: {str(e)}")

@router.post("/deactivate/{price_id}")
async def deactivate_price(
    price_id: str,
    stripe_client: StripeClient = Depends(get_stripe_client)
):
    """Deactivate a price in Stripe"""
    try:
        price = await stripe_client.prices.update_async(
            price_id,
            active=False
        )
        return {"status": "success", "price_id": price.id, "active": price.active}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Price deactivation failed: {str(e)}")

@router.get("/verify-env-prices")
async def verify_environment_prices(
    stripe_client: StripeClient = Depends(get_stripe_client)
):
    """Verify all price IDs defined in environment variables"""
    env_prices = {
        "TREATMENT_PLAN_PRICE_ID": settings.TREATMENT_PLAN_PRICE_ID,
        "IMAGE_CREDIT_10": "price_1Rw6mNFjPe0daNEdfsPGLoJd",
        "IMAGE_CREDIT_20": "price_1Rw6m4FjPe0daNEd6cHUlvMv",
        "IMAGE_CREDIT_50": "price_1Rw6lbFjPe0daNEdhpCC0iTv"
    }
    
    results = {}
    for name, price_id in env_prices.items():
        try:
            price = await stripe_client.prices.retrieve_async(price_id)
            results[name] = {
                "status": "exists",
                "price_id": price.id,
                "active": price.active,
                "product": price.product
            }
        except Exception as e:
            results[name] = {
                "status": "missing",
                "error": str(e),
                "price_id": price_id
            }
    
    return results