from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "withdraw_methods" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL PRIMARY KEY,
    "method_type" VARCHAR(50) NOT NULL,
    "details" JSONB NOT NULL,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
        ALTER TABLE "withdrawal_requests" ADD "withdraw_method_id" UUID;
        ALTER TABLE "withdrawal_requests" ADD "rejection_reason" TEXT;
        ALTER TABLE "withdrawal_requests" ADD CONSTRAINT "fk_withdraw_withdraw_a18f2f48" FOREIGN KEY ("withdraw_method_id") REFERENCES "withdraw_methods" ("id") ON DELETE SET NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "withdrawal_requests" DROP CONSTRAINT IF EXISTS "fk_withdraw_withdraw_a18f2f48";
        ALTER TABLE "withdrawal_requests" DROP COLUMN "withdraw_method_id";
        ALTER TABLE "withdrawal_requests" DROP COLUMN "rejection_reason";
        DROP TABLE IF EXISTS "withdraw_methods";"""
