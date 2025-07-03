from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "users" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" SERIAL NOT NULL PRIMARY KEY,
    "full_name" VARCHAR(100) NOT NULL,
    "email" VARCHAR(100) NOT NULL UNIQUE,
    "password" VARCHAR(255) NOT NULL,
    "agreed_to_toc" BOOL NOT NULL DEFAULT False,
    "is_admin" BOOL NOT NULL DEFAULT False,
    "verification_token" VARCHAR(255),
    "reset_token" VARCHAR(255),
    "stripe_customer_id" VARCHAR(200),
    "subscription_status" VARCHAR(50) DEFAULT 'active',
    "subscription_id" VARCHAR(100),
    "current_plan" VARCHAR(100),
    "next_billing_date" TIMESTAMPTZ,
    "last_processed_event_ts" TIMESTAMPTZ,
    "secret_key" VARCHAR(100)
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """
