from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "uploaded_files" DROP CONSTRAINT IF EXISTS "fk_uploaded_messages_cb03639c";
        ALTER TABLE "uploaded_files" DROP COLUMN "message_id";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "uploaded_files" ADD "message_id" INT;
        ALTER TABLE "uploaded_files" ADD CONSTRAINT "fk_uploaded_messages_cb03639c" FOREIGN KEY ("message_id") REFERENCES "messages" ("id") ON DELETE SET NULL;"""
