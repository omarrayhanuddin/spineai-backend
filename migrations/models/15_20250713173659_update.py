from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "usages" ADD "usage_type" VARCHAR(10) NOT NULL;
        ALTER TABLE "usages" DROP COLUMN "is_message";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "usages" ADD "is_message" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "usages" DROP COLUMN "usage_type";"""
