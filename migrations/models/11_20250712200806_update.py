from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "images" ADD "file_type" VARCHAR(10);
        ALTER TABLE "images" ADD "meta_data" JSONB;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "images" DROP COLUMN "file_type";
        ALTER TABLE "images" DROP COLUMN "meta_data";"""
