from tortoise import fields
from app.models.base import BaseModelWithoutID
from app.utils.helpers import get_password_hash, generate_token, generate_secret_key
from datetime import datetime, timezone
from tortoise import Tortoise


class User(BaseModelWithoutID):
    id = fields.IntField(primary_key=True)
    full_name = fields.CharField(max_length=100)
    email = fields.CharField(max_length=100, unique=True)
    password = fields.CharField(max_length=255)
    agreed_to_toc = fields.BooleanField(default=False)
    is_admin = fields.BooleanField(default=False)
    verification_token = fields.CharField(max_length=255, null=True)
    reset_token = fields.CharField(max_length=255, null=True)
    stripe_customer_id = fields.CharField(max_length=200, null=True)
    subscription_status = fields.CharField(max_length=50, null=True, default="active")
    subscription_id = fields.CharField(max_length=100, null=True)
    current_plan = fields.CharField(max_length=100, null=True)
    next_billing_date = fields.DatetimeField(null=True)
    last_processed_event_ts = fields.DatetimeField(null=True)
    secret_key = fields.CharField(
        default=generate_secret_key, max_length=100, null=True
    )

    class Meta:
        table = "users"

    @property
    def is_verified(self):
        return False if self.verification_token else True

    async def monthly_page_limit_exceeded(self) -> tuple[bool, int | None, str | None]:
        from app.models.payment import Plan

        conn = Tortoise.get_connection("default")
        now_utc = datetime.now(timezone.utc)
        start_of_month_utc = now_utc.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        result = await conn.execute_query_dict(
            """
            SELECT SUM(usage_count) AS total
            FROM usages
            WHERE user_id = $1
            AND is_message = FALSE
            AND created_at BETWEEN $2 AND $3;
        """,
            [self.id, start_of_month_utc, now_utc],
        )

        total_page_count = (
            result[0]["total"] or 0 if result and result[0]["total"] is not None else 0
        )

        plan = await Plan.get_or_none(stripe_price_id=self.current_plan)
        if not plan or plan.page_limit is None:
            return False, None, None

        exceeded = total_page_count >= plan.page_limit
        return exceeded, plan.page_limit, plan.name

    async def monthly_message_limit_exceeded(
        self,
    ) -> tuple[bool, int | None, str | None]:
        from app.models.payment import Plan

        conn = Tortoise.get_connection("default")
        now_utc = datetime.now(timezone.utc)

        plan = await Plan.get_or_none(stripe_price_id=self.current_plan)
        if not plan or plan.message_limit is None:
            return False, None, None

        is_free_plan = "free" in plan.name.lower()
        start_time = (
            now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
            if is_free_plan
            else now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        )

        result = await conn.execute_query_dict(
            """
            SELECT SUM(usage_count) AS total
            FROM usages
            WHERE user_id = $1
            AND is_message = TRUE
            AND created_at BETWEEN $2 AND $3;
        """,
            [self.id, start_time, now_utc],
        )

        total_message_count = (
            result[0]["total"] or 0 if result and result[0]["total"] is not None else 0
        )
        exceeded = total_message_count >= plan.message_limit
        return exceeded, plan.message_limit, plan.name

    async def save(self, *args, **kwargs):
        if not self.pk:
            self.password = get_password_hash(self.password)
            self.verification_token = generate_token()
        await super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name
