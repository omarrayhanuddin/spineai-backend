from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" ADD "has_bought_ebook" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "users" ADD "referral_balance" DOUBLE PRECISION NOT NULL DEFAULT 0;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" DROP COLUMN "has_bought_ebook";
        ALTER TABLE "users" DROP COLUMN "referral_balance";"""
