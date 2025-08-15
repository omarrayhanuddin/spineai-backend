from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "uploaded_files" ALTER COLUMN "message_id" SET NOT NULL;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "uploaded_files" ALTER COLUMN "message_id" DROP NOT NULL;"""
