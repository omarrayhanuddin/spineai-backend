from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.dependency import get_current_user, get_stripe_client, get_current_admin
from app.models.user import User, CouponCode
from app.models.payment import Plan, PendingEvent
from app.schemas.payment import PlanOut, PlanIn
from app.core.config import settings
from tortoise.transactions import in_transaction
from datetime import datetime, timezone
from stripe import StripeClient, Webhook, SignatureVerificationError
from pydantic import BaseModel
from fastapi import BackgroundTasks
from typing import Optional
from app.services.email_service import send_email
import random
import string

from enum import Enum
from typing import Dict


router = APIRouter(prefix="/v1/payment", tags=["Payment Endpoints"])

# Request model for create-session endpoint
class CreateSessionRequest(BaseModel):
    product_name: str
    coupon_code: str | None = None
def generate_coupon_code(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

class EbookPurchaseRequest(BaseModel):
    email: str | None = None
@router.get("/plan/all", response_model=list[PlanOut])
async def plans():
    return await Plan.all()

class ImageCreditPackage(str, Enum):
    TEN = "10"
    TWENTY = "20"
    FIFTY = "50"

IMAGE_CREDIT_PRODUCTS: Dict[ImageCreditPackage, str] = {
    ImageCreditPackage.TEN: "prod_SrUBnwPCjVywBP",
    ImageCreditPackage.TWENTY: "prod_SrUDzttTeg2SXE",
    ImageCreditPackage.FIFTY: "prod_SrUFaLHUwiRgUO"
}

class ImageCreditPurchaseRequest(BaseModel):
    email: str
    package: ImageCreditPackage
    customer_name: Optional[str] = "Customer"
    

@router.post(
    "/plan/create", response_model=PlanOut, dependencies=[Depends(get_current_admin)]
)
async def plan_create(form: PlanIn):
    if await Plan.exists(name=form.name):
        raise HTTPException(400, "Plan with this name already exists")
    if await Plan.exists(stripe_price_id=form.stripe_price_id):
        raise HTTPException(400, "Plan with this name already exists")
    return await Plan.create(**form.model_dump())


@router.post(
    "/plan/{plan_id}/update",
    response_model=PlanOut,
    dependencies=[Depends(get_current_admin)],
)
async def plan_update(plan_id: str, form: PlanIn):
    plan = await Plan.get_or_none(id=plan_id)
    if plan is None:
        raise HTTPException(400, "Plan with this id does not exists")
    return await plan.update_from_dict(form.model_dump(exclude_unset=True))


async def _resolve_discounts(stripe_client: StripeClient, code: str) -> list[dict]:
    """
    Accepts:
      - Human-friendly promotion code text (e.g. 'SUMMER20')
      - Promotion code id: 'promo_...'
      - Coupon id: 'coupon_...'
    Returns a Stripe 'discounts' array suitable for checkout.sessions.create.
    Raises HTTPException(400) if invalid/inactive.
    """
    code = (code or "").strip()
    if not code:
        return []

    # If it's clearly a promotion code id
    if code.startswith("promo_"):
        try:
            promo = await stripe_client.promotion_codes.retrieve_async(code)
        except Exception:
            raise HTTPException(400, "Invalid promotion code")
        if not getattr(promo, "active", False):
            raise HTTPException(400, "Promotion code is inactive or expired")
        return [{"promotion_code": promo.id}]

    # If it's clearly a coupon id
    if code.startswith("coupon_"):
        try:
            coupon = await stripe_client.coupons.retrieve_async(code)
        except Exception:
            raise HTTPException(400, "Invalid coupon")
        if not getattr(coupon, "valid", False):
            raise HTTPException(400, "Coupon is inactive or expired")
        return [{"coupon": coupon.id}]

    # Otherwise, treat it as human-readable promotion code text
    try:
        promos = await stripe_client.promotion_codes.list_async(
            {"code": code, "active": True, "limit": 1}
        )
    except Exception:
        raise HTTPException(400, "Could not validate coupon/promotion code")
    if getattr(promos, "data", []):
        return [{"promotion_code": promos.data[0].id}]

    raise HTTPException(400, "Invalid or expired coupon/promotion code")


@router.post("/create-session")
async def create_session(
    request: CreateSessionRequest,
    user: User = Depends(get_current_user),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    
    product_name = request.product_name
    coupon_code = request.coupon_code
    plan = await Plan.get_or_none(name=product_name)
    if not plan:
        raise HTTPException(400, "Product not found")
    product_id = plan.stripe_price_id
    if not user.stripe_customer_id or user.stripe_customer_id.strip() == "":
        customer = await stripe_client.customers.create_async(
            {"name": user.full_name, "email": user.email}
        )
        user.stripe_customer_id = customer.id

    if user.subscription_id:
        session = await stripe_client.billing_portal.sessions.create_async(
            {"customer": user.stripe_customer_id, "return_url": settings.STRIPE_SUCCESS_URL}
        )
        return {"checkout_url": session.url}

    # Build checkout params
    params = {
        "success_url": settings.STRIPE_SUCCESS_URL,
        "cancel_url": settings.STRIPE_CANCEL_URL,
        "mode": "subscription",
        "line_items": [{"price": product_id, "quantity": 1}],
        "customer": user.stripe_customer_id,
    }

    # Apply discount if provided
    if coupon_code and not user.coupon_used:
        params["discounts"] = await _resolve_discounts(stripe_client, coupon_code)

    try:
        session = await stripe_client.checkout.sessions.create_async(params=params)
    except Exception as e:
        raise HTTPException(400, str(e))

    return {"checkout_url": session.url}


@router.get("/customer-portal")
async def get_customer_portal(
    user: User = Depends(get_current_user),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    if not user.stripe_customer_id:
        raise HTTPException(400, "Stripe customer not found.")

    session = await stripe_client.billing_portal.sessions.create_async(
        {"customer": user.stripe_customer_id, "return_url": settings.STRIPE_SUCCESS_URL}
    )
    return {"portal_url": session.url}



@router.post("/buy/ebook")
async def buy_ebook(
    request: EbookPurchaseRequest,
    background_tasks: BackgroundTasks,
    # user: User = Depends(get_current_user),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """
    Endpoint for purchasing an ebook.
    - Creates a Stripe checkout session
    - Sends confirmation email with coupon after successful payment
    """
    try:
        # Use authenticated user's email unless specifically overridden
        customer_email = request.email if request.email else user.email
        
        # Create Stripe checkout session
        session = await stripe_client.checkout.sessions.create_async({
            "success_url": f"{settings.STRIPE_SUCCESS_URL}?product=ebook",
            "cancel_url": settings.STRIPE_CANCEL_URL,
            "payment_method_types": ["card"],
            "line_items": [{
                "price": settings.EBOOK_PRICE_ID,
                "quantity": 1,
            }],
            "mode": "payment",
            "customer_email": customer_email,
            "metadata": {
                "user_id": str(user.id),
                "product_type": "ebook"
            }
        })
        
        return {"checkout_url": session.url}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/buy/image-credits")
async def buy_image_credits(
    request: ImageCreditPurchaseRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),  
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """
    Endpoint for purchasing image credits
    - Creates a Stripe checkout session
    - Sends confirmation email with purchased credits
    """
    try:
        price_id = IMAGE_CREDIT_PRODUCTS[request.package]
        
        session_params = {
            "success_url": f"{settings.STRIPE_SUCCESS_URL}?product=image_credits&quantity={request.package}",
            "cancel_url": settings.STRIPE_CANCEL_URL,
            "payment_method_types": ["card"],
            "line_items": [{
                "price": price_id,
                "quantity": 1,
            }],
            "mode": "payment",
            "metadata": {
                "product_type": "image_credits",
                "credit_amount": request.package.value,
                "customer_name": request.customer_name,
                "customer_email": request.email,
            }
        }

        if user and user.stripe_customer_id:
            session_params["customer"] = user.stripe_customer_id
        else:
            session_params["customer_email"] = request.email
        session = await stripe_client.checkout.sessions.create_async(session_params)
        
        return {
            "checkout_url": session.url,
            "credit_amount": request.package.value
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Image credit purchase failed: {str(e)}"
        )
@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request, 
    background_tasks: BackgroundTasks,
    stripe_client: StripeClient = Depends(get_stripe_client)
):
    # Validate webhook signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = Webhook.construct_event(
            payload, 
            sig_header, 
            settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    event_id = event["id"]
    event_type = event["type"]
    created_ts = datetime.fromtimestamp(event["created"], tz=timezone.utc)
    data = event["data"]["object"]
    customer_id = data.get("customer")

    async with in_transaction():
        # Idempotency check
        existing_event = await PendingEvent.get_or_none(id=event_id, processed=True)
        if existing_event:
            return {"status": "success"}

        # Handle checkout.session.completed events
        if event_type == "checkout.session.completed":
            session = data
            metadata = session.get("metadata", {})
            
            # Ebook purchase flow
            if metadata.get("product_type") == "ebook":
                user_email = session["customer_email"]
                coupon_code = generate_coupon_code()
                
                # Send ebook confirmation email
                background_tasks.add_task(
                    send_email,
                    subject="Your E-Book Purchase Confirmation",
                    recipient=user_email,
                    template_name="ebook_purchase.html",
                    context={
                        "coupon_code": coupon_code,
                        "company_name": "SpineAi",
                        "support_email": settings.SUPPORT_EMAIL,
                        "discount_percentage": "20%",
                        "current_year": datetime.now().year
                    }
                )
                
                # Create and store the coupon
                await CouponCode.create(
                    code=coupon_code,
                    discount_percent=20,
                    valid_until=datetime.now() + timedelta(days=30),
                    email=user_email
                )
                
                await PendingEvent.create(
                    id=event_id,
                    type=event_type,
                    created=created_ts,
                    payload=event,
                    processed=True
                )
                return {"status": "success"}
            
            # Image credits purchase flow
            elif metadata.get("product_type") == "image_credits":
                user_email = session["customer_email"]
                credit_amount = metadata.get("credit_amount", "10")
                
                # Send image credits confirmation email
                background_tasks.add_task(
                    send_email,
                    subject=f"Your {credit_amount} Image Credits Purchase",
                    recipient=user_email,
                    template_name="image_credits_purchase.html",
                    context={
                        "credit_amount": credit_amount,
                        "company_name": "SpineAi",
                        "support_email": settings.SUPPORT_EMAIL,
                        "current_year": datetime.now().year
                    }
                )
                
                # Here you would typically add credits to the user's account
                # Example: await add_image_credits(user_email, int(credit_amount))
                
                await PendingEvent.create(
                    id=event_id,
                    type=event_type,
                    created=created_ts,
                    payload=event,
                    processed=True
                )
                return {"status": "success"}

        # Handle customer events (subscriptions)
        user = await User.get_or_none(stripe_customer_id=customer_id)

        if not user:
            await PendingEvent.get_or_create(
                id=event_id,
                defaults={
                    "type": event_type,
                    "created": created_ts,
                    "payload": event,
                    "processed": False,
                },
            )
            return {"status": "success"}

        # Skip older events
        if user.last_processed_event_ts and created_ts <= user.last_processed_event_ts:
            await PendingEvent.get_or_create(
                id=event_id,
                defaults={
                    "type": event_type,
                    "created": created_ts,
                    "payload": event,
                    "processed": False,
                },
            )
            return {"status": "success"}

        # Process subscription events
        try:
            if event_type.startswith("customer.subscription."):
                subscription_id = data.get("id")
                status = data.get("status")
                plan_id = (
                    data.get("items", {})
                    .get("data", [{}])[0]
                    .get("price", {})
                    .get("id")
                )
                period_end_ts = (
                    data.get("items", {})
                    .get("data", [{}])[0]
                    .get("current_period_end")
                )
                current_period_end = (
                    datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
                    if period_end_ts
                    else None
                )

                if event_type == "customer.subscription.created" and not user.coupon_used:
                    user.coupon_used = True

                if event_type == "customer.subscription.deleted":
                    user.subscription_status = "active"
                    user.subscription_id = None
                    user.next_billing_date = None
                    user.current_plan = None
                else:
                    user.subscription_status = status
                    user.subscription_id = subscription_id
                    user.current_plan = plan_id
                    user.next_billing_date = current_period_end

            elif event_type == "invoice.payment_succeeded":
                period_end = (
                    data.get("lines", {})
                    .get("data", [{}])[0]
                    .get("period", {})
                    .get("end")
                )
                next_billing_date = (
                    datetime.fromtimestamp(period_end, tz=timezone.utc)
                    if period_end
                    else None
                )
                user.subscription_status = "active"
                if next_billing_date:
                    user.next_billing_date = next_billing_date

            elif event_type == "invoice.payment_failed":
                user.subscription_status = "past_due"

            elif event_type == "payment_method.attached":
                user.has_valid_card = True

            user.last_processed_event_ts = created_ts
            await user.save()

            await PendingEvent.get_or_create(
                id=event_id,
                defaults={
                    "type": event_type,
                    "created": created_ts,
                    "payload": event,
                    "processed": True,
                },
            )

        except Exception as e:
            print(f"Error processing event {event_id}: {str(e)}")
            await PendingEvent.get_or_create(
                id=event_id,
                defaults={
                    "type": event_type,
                    "created": created_ts,
                    "payload": event,
                    "processed": False,
                },
            )
            return {"status": "success"}

    return {"status": "success"}