from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" ADD "allow_push_notifications" BOOL NOT NULL DEFAULT True;
        ALTER TABLE "users" ADD "allow_email_notifications" BOOL NOT NULL DEFAULT True;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" DROP COLUMN "allow_push_notifications";
        ALTER TABLE "users" DROP COLUMN "allow_email_notifications";"""
