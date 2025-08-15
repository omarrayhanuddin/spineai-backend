from fastapi import APIRouter, Depends, HTTPException, Request, Body
from app.api.dependency import get_current_user, get_stripe_client, get_current_admin
from app.models.user import User
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
import os
import json
from enum import Enum


router = APIRouter(prefix="/v1/payment", tags=["Payment Endpoints"])
file_path = "stage_plans.json"


def load_plan_data():
    """
    Reads the data.json file, extracts the image_credit_products object,
    and returns it. Raises exceptions on failure.
    """
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
            return data
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Error: The file '{file_path}' was not found. Please ensure the file exists."
        )
    except json.JSONDecodeError:
        raise ValueError(
            f"Error: Could not decode JSON from '{file_path}'. Please check the file's format."
        )


json_data = load_plan_data()
image_credit_products = json_data.get("image_credit_products", {})


# Request model for create-session endpoint
class CreateSessionRequest(BaseModel):
    product_name: str
    coupon_code: str | None = None


class ImageCreditPackage(str, Enum):
    TEN = "10"
    TWENTY = "20"
    FIFTY = "50"


@router.get("/plan/all", response_model=list[PlanOut])
async def plans():
    return await Plan.all()


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
            {
                "customer": user.stripe_customer_id,
                "return_url": settings.STRIPE_SUCCESS_URL,
            }
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
    customer_email=Body(..., embed=True),
    full_name: Optional[str] = Body(None, embed=True),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """
    Endpoint for purchasing an ebook.
    - Creates a Stripe checkout session with price_1Rw6l6FjPe0daNEdWIXX4Cfl
    - After successful payment, sends confirmation email with:
      - Thank you message
      - Download link for the ebook
      - 20% discount coupon for future purchases
    """
    try:
        customer_email = customer_email.strip()

        session_params = {
            "success_url": f"{settings.STRIPE_SUCCESS_URL}?product=ebook",
            "cancel_url": settings.STRIPE_CANCEL_URL,
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price": json_data.get("ebook_products", {}).get("1"),
                    "quantity": 1,
                }
            ],
            "mode": "payment",
            "metadata": {
                "product_type": "ebook",
                "customer_email": customer_email,
                "customer_name": full_name or "Ebook Customer",
            },
        }
        user = await User.get_or_none(email=customer_email)

        if user:
            session_params["metadata"]["user_id"] = str(user.id)
            if user.stripe_customer_id:
                session_params["customer"] = user.stripe_customer_id
            else:
                # Create customer if doesn't exist
                customer = await stripe_client.customers.create_async(
                    {
                        "name": getattr(user, "full_name", "Ebook Customer"),
                        "email": customer_email,
                    }
                )
                session_params["customer"] = customer.id
        else:
            session_params["customer_email"] = customer_email

        session = await stripe_client.checkout.sessions.create_async(session_params)

        return {"checkout_url": session.url}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/buy/image-credits")
async def buy_image_credits(
    package: ImageCreditPackage = Body(..., embed=True),
    user: User = Depends(get_current_user),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """
    Endpoint for purchasing image credits
    - Creates a Stripe checkout session
    - Sends confirmation email with purchased credits
    """
    try:
        # price_id = IMAGE_CREDIT_PRODUCTS[package]
        price_id = image_credit_products.get(package, None)

        session_params = {
            "success_url": f"{settings.STRIPE_SUCCESS_URL}?product=image_credits&quantity={package}",
            "cancel_url": settings.STRIPE_CANCEL_URL,
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "mode": "payment",
            "metadata": {
                "product_type": "image_credits",
                "credit_amount": package.value,
                "customer_name": user.full_name,
                "customer_email": user.email,
            },
        }
        session_params["customer"] = user.stripe_customer_id
        session = await stripe_client.checkout.sessions.create_async(session_params)

        return {"checkout_url": session.url, "credit_amount": package.value}

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Image credit purchase failed: {str(e)}"
        )


@router.post("/webhook/stripe")
async def handle_stripe_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    """
    Handle all Stripe webhook events with idempotency checks.
    Processes:
    - Successful payments (ebook and image credits)
    - Subscription events
    - Payment failures
    """
    # 1. Verify the webhook signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        raise HTTPException(400, "Invalid payload")
    except SignatureVerificationError as e:
        raise HTTPException(400, "Invalid signature")
    except Exception as e:
        raise HTTPException(400, f"Webhook error: {str(e)}")

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]
    created_ts = datetime.fromtimestamp(event["created"], tz=timezone.utc)

    # 2. Process the event based on type
    async with in_transaction():
        # Idempotency check
        if await PendingEvent.filter(id=event_id, processed=True).exists():
            return {"status": "already processed"}

        # Handle checkout.session.completed events
        if event_type == "checkout.session.completed":
            return await handle_checkout_session(
                data, background_tasks, event_id, event_type, created_ts
            )

        # Handle subscription events
        if event_type.startswith("customer.subscription."):
            return await handle_subscription_event(
                data, event_id, event_type, created_ts
            )

        # Handle invoice events
        if event_type.startswith("invoice."):
            return await handle_invoice_event(data, event_id, event_type, created_ts)

        # For unhandled events, just mark as processed
        await PendingEvent.create(
            id=event_id,
            type=event_type,
            created=created_ts,
            payload=event,
            processed=True,
        )
        return {"status": "processed - no action"}


async def handle_checkout_session(
    session: dict,
    background_tasks: BackgroundTasks,
    event_id: str,
    event_type: str,
    created_ts: datetime,
) -> dict:
    """Handle completed checkout sessions"""
    metadata = session.get("metadata", {})
    payment_status = session.get("payment_status")

    # Only process successful payments
    if payment_status != "paid":
        await PendingEvent.create(
            id=event_id,
            type=event_type,
            created=created_ts,
            payload={"session": session},
            processed=True,
        )
        return {"status": "skipped - payment not successful"}

    # Ebook purchase flow
    if metadata.get("product_type") == "ebook":
        return await handle_ebook_purchase(
            session, metadata, background_tasks, event_id, event_type, created_ts
        )

    # Image credits purchase flow
    elif metadata.get("product_type") == "image_credits":
        return await handle_image_credits_purchase(
            session, metadata, background_tasks, event_id, event_type, created_ts
        )

    # Unknown product type
    await PendingEvent.create(
        id=event_id,
        type=event_type,
        created=created_ts,
        payload={"session": session},
        processed=True,
    )
    return {"status": "processed - unknown product type"}


async def handle_ebook_purchase(
    session: dict,
    metadata: dict,
    background_tasks: BackgroundTasks,
    event_id: str,
    event_type: str,
    created_ts: datetime,
) -> dict:
    """Process ebook purchase and send confirmation email"""
    user_email = session.get("customer_email") or metadata.get("customer_email")
    if not user_email:
        raise HTTPException(400, "No email provided for ebook purchase")

    coupon_code = "DISCOUNT101"
    pdf_path = os.path.join("app", "static", "files", "ebook.pdf")

    # Prepare and send email
    context = {
        "coupon_code": coupon_code,
        "customer_name": metadata.get("customer_name", "Ebook Customer"),
        "discount_percentage": "20%",
        "support_email": settings.SUPPORT_EMAIL,
        "company_name": "SpineAi",
        "current_year": datetime.now().year,
    }

    background_tasks.add_task(
        send_email,
        subject="Your E-Book Purchase Confirmation",
        recipient=user_email,
        template_name="ebook_purchase.html",
        context=context,
        attachments=[pdf_path] if os.path.exists(pdf_path) else None,
    )

    await PendingEvent.create(
        id=event_id,
        type=event_type,
        created=created_ts,
        payload={"session": session},
        processed=True,
    )
    return {"status": "success - ebook email sent"}


async def handle_image_credits_purchase(
    session: dict,
    metadata: dict,
    background_tasks: BackgroundTasks,
    event_id: str,
    event_type: str,
    created_ts: datetime,
) -> dict:
    """Process image credits purchase and send confirmation"""
    customer_id = session.get("customer")
    if not customer_id:
        raise HTTPException(400, "No customer ID found in session")
    user = await User.get_or_none(stripe_customer_id=customer_id)
    if not user:
        raise HTTPException(400, "User not found for the provided customer ID")

    credit_amount = int(metadata.get("credit_amount", 10))

    # Prepare and send email
    context = {
        "credit_amount": credit_amount,
        "support_email": settings.SUPPORT_EMAIL,
        "company_name": "SpineAi",
        "current_year": datetime.now().year,
    }

    background_tasks.add_task(
        send_email,
        subject=f"Your {credit_amount} Image Credits Purchase",
        recipient=user.email,
        template_name="image_credits_purchase.html",
        context=context,
    )

    user.image_credit += credit_amount
    await user.save()

    await PendingEvent.create(
        id=event_id,
        type=event_type,
        created=created_ts,
        payload={"session": session},
        processed=True,
    )
    return {"status": "success - credits email sent"}


async def handle_subscription_event(
    subscription: dict, event_id: str, event_type: str, created_ts: datetime
) -> dict:
    """Handle subscription lifecycle events"""
    customer_id = subscription.get("customer")
    if not customer_id:
        await PendingEvent.create(
            id=event_id,
            type=event_type,
            created=created_ts,
            payload={"subscription": subscription},
            processed=True,
        )
        return {"status": "processed - no customer"}

    user = await User.get_or_none(stripe_customer_id=customer_id)
    if not user:
        await PendingEvent.create(
            id=event_id,
            type=event_type,
            created=created_ts,
            payload={"subscription": subscription},
            processed=True,
        )
        return {"status": "processed - user not found"}

    # Skip older events
    if user.last_processed_event_ts and created_ts <= user.last_processed_event_ts:
        await PendingEvent.create(
            id=event_id,
            type=event_type,
            created=created_ts,
            payload={"subscription": subscription},
            processed=True,
        )
        return {"status": "skipped - older event"}

    # Update subscription status
    if event_type == "customer.subscription.deleted":
        user.subscription_status = "active"
        user.subscription_id = None
        user.next_billing_date = None
        user.current_plan = None
    else:
        user.subscription_status = subscription.get("status", "active")
        user.subscription_id = subscription.get("id")
        user.current_plan = (
            subscription.get("items", {})
            .get("data", [{}])[0]
            .get("price", {})
            .get("id")
        )
        period_end = (
            subscription.get("items", {}).get("data", [{}])[0].get("current_period_end")
        )
        if period_end:
            user.next_billing_date = datetime.fromtimestamp(period_end, tz=timezone.utc)

    user.last_processed_event_ts = created_ts
    await user.save()

    await PendingEvent.create(
        id=event_id,
        type=event_type,
        created=created_ts,
        payload={"subscription": subscription},
        processed=True,
    )
    return {"status": "success - subscription updated"}


async def handle_invoice_event(
    invoice: dict, event_id: str, event_type: str, created_ts: datetime
) -> dict:
    """Handle invoice payment events"""
    customer_id = invoice.get("customer")
    if not customer_id:
        await PendingEvent.create(
            id=event_id,
            type=event_type,
            created=created_ts,
            payload={"invoice": invoice},
            processed=True,
        )
        return {"status": "processed - no customer"}

    user = await User.get_or_none(stripe_customer_id=customer_id)
    if not user:
        await PendingEvent.create(
            id=event_id,
            type=event_type,
            created=created_ts,
            payload={"invoice": invoice},
            processed=True,
        )
        return {"status": "processed - user not found"}

    if event_type == "invoice.payment_succeeded":
        period_end = (
            invoice.get("lines", {}).get("data", [{}])[0].get("period", {}).get("end")
        )
        if period_end:
            user.next_billing_date = datetime.fromtimestamp(period_end, tz=timezone.utc)
        user.subscription_status = "active"
    elif event_type == "invoice.payment_failed":
        user.subscription_status = "past_due"

    await user.save()

    await PendingEvent.create(
        id=event_id,
        type=event_type,
        created=created_ts,
        payload={"invoice": invoice},
        processed=True,
    )
    return {"status": "success - invoice processed"}
