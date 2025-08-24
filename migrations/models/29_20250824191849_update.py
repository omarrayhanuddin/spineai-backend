from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" ADD "affiliate_id" VARCHAR(30);
        ALTER TABLE "users" ADD "referrer_bonus_applied" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "users" ADD "refferred_by" VARCHAR(30);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" DROP COLUMN "affiliate_id";
        ALTER TABLE "users" DROP COLUMN "referrer_bonus_applied";
        ALTER TABLE "users" DROP COLUMN "refferred_by";"""
