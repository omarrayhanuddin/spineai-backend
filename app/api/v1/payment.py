from fastapi import APIRouter, Depends, HTTPException, Request
from app.api.dependency import get_current_user, get_stripe_client, get_current_admin
from app.models.user import User
from app.models.payment import Plan, PendingEvent
from app.schemas.payment import PlanOut, PlanIn
from app.core.config import settings
from tortoise.transactions import in_transaction
from datetime import datetime, timezone
from stripe import StripeClient, Webhook, SignatureVerificationError


router = APIRouter(prefix="/v1/payment", tags=["Payment Endpoints"])


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


@router.post("/stripe/create-session/{product_id}")
async def create_session(
    product_id: str,
    cupon_code: str = None,
    user: User = Depends(get_current_user),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    if user.stripe_customer_id is None or user.stripe_customer_id.strip() == "":
        customer = await stripe_client.customers.create_async(
            {"name": user.full_name, "email": user.email}
        )
        user.stripe_customer_id = customer.id
        await user.save()
    if user.subscription_id:
        session = await stripe_client.billing_portal.sessions.create_async(
            {
                "customer": user.stripe_customer_id,
                "return_url": settings.STRIPE_SUCCESS_URL,
            }
        )
        return {"checkout_url": session.url}
    params = {
        "success_url": settings.STRIPE_SUCCESS_URL,
        "cancel_url": settings.STRIPE_CANCEL_URL,
        "mode": "subscription",
        "line_items": [{"price": product_id, "quantity": 1}],
        "customer": user.stripe_customer_id,
    }
    if cupon_code is not None:
        params["discounts"] = [{"coupon": cupon_code}]
    try:
        session = await stripe_client.checkout.sessions.create_async(params=params)
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"checkout_url": session.url}


@router.get("/stripe/customer-portal")
async def get_customer_portal(
    user: User = Depends(get_current_user),
    stripe_client: StripeClient = Depends(get_stripe_client),
):
    if not user.stripe_customer_id:
        raise HTTPException(400, "Stripe customer not found.")

    session = await stripe_client.billing_portal.sessions.create_async(
        {
            "customer": user.stripe_customer_id,
            "return_url": settings.STRIPE_SUCCESS_URL,
        }
    )
    return {"portal_url": session.url}


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request, stripe_client: StripeClient = Depends(get_stripe_client)
):
    # Validate webhook signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = Webhook.construct_event(payload, sig_header, webhook_secret)
    except SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    event_id = event["id"]
    event_type = event["type"]
    # Convert Stripe timestamp to UTC-aware datetime
    created_ts = datetime.fromtimestamp(event["created"], tz=timezone.utc)
    data = event["data"]["object"]
    customer_id = data.get("customer")

    async with in_transaction():
        # Check for idempotency
        existing_event = await PendingEvent.get_or_none(id=event_id, processed=True)
        if existing_event:
            return {"status": "success"}

        user = await User.get_or_none(stripe_customer_id=customer_id)

        if not user:
            # Store event if user doesn't exist (e.g., customer.created not processed)
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

        # Check if event can be processed (timestamp > last_processed_event_ts)
        if user.last_processed_event_ts and created_ts <= user.last_processed_event_ts:
            # Store in PendingEvent for later processing
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

        # Process the event
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
                    data.get("items", {}).get("data", [{}])[0].get("current_period_end")
                )
                current_period_end = (
                    datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
                    if period_end_ts
                    else None
                )

                if event_type == "customer.subscription.deleted":
                    free_plan = await Plan.get_or_none(name__iexact="free")
                    if free_plan:
                        user.subscription_status = "active"
                        user.subscription_id = None
                        user.next_billing_date = None
                        user.current_plan = free_plan.stripe_price_id
                    else:
                        print(f"Free plan not found for user {customer_id}")
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

            # Update last processed event timestamp and save user
            user.last_processed_event_ts = created_ts
            await user.save()

            # Mark event as processed
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
