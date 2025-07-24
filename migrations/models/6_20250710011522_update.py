from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "notifications" ADD "session_id" UUID NOT NULL;
        ALTER TABLE "notifications" ADD CONSTRAINT "fk_notifica_sessions_2bdaa143" FOREIGN KEY ("session_id") REFERENCES "sessions" ("id") ON DELETE CASCADE;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "notifications" DROP CONSTRAINT IF EXISTS "fk_notifica_sessions_2bdaa143";
        ALTER TABLE "notifications" DROP COLUMN "session_id";"""
