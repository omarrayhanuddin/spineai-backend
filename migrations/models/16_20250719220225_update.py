from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "plans" ADD "weekly_reminder" BOOL NOT NULL DEFAULT False;
        ALTER TABLE "plans" ADD "file_limit" INT NOT NULL DEFAULT 1;
        ALTER TABLE "plans" ADD "chat_model" VARCHAR(20);
        ALTER TABLE "plans" ADD "image_limit" INT NOT NULL DEFAULT 2;
        ALTER TABLE "plans" ADD "message_limit" INT NOT NULL DEFAULT 20;
        ALTER TABLE "plans" ADD "treatment_plan" BOOL NOT NULL DEFAULT False;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "plans" DROP COLUMN "weekly_reminder";
        ALTER TABLE "plans" DROP COLUMN "file_limit";
        ALTER TABLE "plans" DROP COLUMN "chat_model";
        ALTER TABLE "plans" DROP COLUMN "image_limit";
        ALTER TABLE "plans" DROP COLUMN "message_limit";
        ALTER TABLE "plans" DROP COLUMN "treatment_plan";"""
