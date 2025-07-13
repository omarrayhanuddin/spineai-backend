from fastapi import HTTPException, status
from tortoise import fields
from app.models.base import BaseModelWithoutID
from app.utils.helpers import get_password_hash, generate_token, generate_secret_key
import asyncio
import logging


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
    coupon_used = fields.BooleanField(default=False)
    secret_key = fields.CharField(
        default=generate_secret_key, max_length=100, null=True
    )
    allow_email_notifications = fields.BooleanField(default=True)
    allow_push_notifications = fields.BooleanField(default=True)

    class Meta:
        table = "users"

    @property
    def is_verified(self):
        return False if self.verification_token else True

    async def check_free_trial_used(self, files=None):
        if files is None:
            files = []
        if self.current_plan not in (None, ""):
            return False
        from app.models.chat import ChatMessage, UserUploadedFile

        # Count uploaded images and non-image files in one pass
        uploaded_image_count = 0
        uploaded_file_count = 0
        image_extensions = {"jpg", "jpeg", "png"}
        for file in files:
            if file.filename and "." in file.filename:
                ext = file.filename.lower().split(".")[-1]
                if ext in image_extensions:
                    uploaded_image_count += 1
                else:
                    uploaded_file_count += 1

        # Run database queries concurrently
        try:
            total_message, total_images, total_files = await asyncio.gather(
                ChatMessage.filter(session__user=self).count(),
                UserUploadedFile.filter(
                    user=self, file_type__in=["jpg", "jpeg", "png"]
                ).count(),
                UserUploadedFile.filter(user=self)
                .exclude(file_type__in=["jpg", "jpeg", "png"])
                .count(),
            )
        except Exception as e:
            logging.error(f"Database query failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error while checking free trial limits",
            )

        # Check limits and raise specific HTTP exceptions
        if total_message >= 30:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Free trial message limit of 30 exceeded",
            )
        if total_images + uploaded_image_count > 3:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Free trial image limit of 3 exceeded",
            )
        if total_files + uploaded_file_count > 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Free trial non-image file limit of 1 exceeded",
            )

        return False

    async def check_coupon_used(self, coupon_code):
        if await self.coupon_codes.filter(coupon_code=coupon_code).exists():
            return True
        return False

    async def save(self, *args, **kwargs):
        if not self.pk:
            self.password = get_password_hash(self.password)
            self.verification_token = generate_token()
        await super().save(*args, **kwargs)

    def __str__(self):
        return self.full_name


class CouponCode(BaseModelWithoutID):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField("models.User", related_name="coupon_codes")
    coupon_code = fields.CharField(max_length=50)

    class Meta:
        table = "coupon_codes"
