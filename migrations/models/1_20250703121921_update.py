from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "pending_stripe_events" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" VARCHAR(255) NOT NULL PRIMARY KEY,
    "type" VARCHAR(255) NOT NULL,
    "created" TIMESTAMPTZ NOT NULL,
    "payload" JSONB NOT NULL,
    "processed" BOOL NOT NULL DEFAULT False
);
        CREATE TABLE IF NOT EXISTS "plans" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(50) NOT NULL UNIQUE,
    "description" TEXT,
    "price" DECIMAL(10,2) NOT NULL,
    "stripe_price_id" VARCHAR(255) NOT NULL UNIQUE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "pending_stripe_events";
        DROP TABLE IF EXISTS "plans";"""
