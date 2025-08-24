from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" ALTER COLUMN "referral_balance" DROP DEFAULT;
        ALTER TABLE "users" ALTER COLUMN "referral_balance" TYPE DECIMAL(10,2) USING "referral_balance"::DECIMAL(10,2);
        ALTER TABLE "users" ALTER COLUMN "referral_balance" TYPE DECIMAL(10,2) USING "referral_balance"::DECIMAL(10,2);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" ALTER COLUMN "referral_balance" TYPE DOUBLE PRECISION USING "referral_balance"::DOUBLE PRECISION;
        ALTER TABLE "users" ALTER COLUMN "referral_balance" SET DEFAULT 0;"""
