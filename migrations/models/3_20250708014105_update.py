from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "sessions" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" UUID NOT NULL PRIMARY KEY,
    "title" TEXT,
    "findings" JSONB,
    "recommendations" JSONB,
    "is_diagnosed" BOOL NOT NULL DEFAULT False,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);
        CREATE TABLE IF NOT EXISTS "messages" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" SERIAL NOT NULL PRIMARY KEY,
    "sender" VARCHAR(10) NOT NULL,
    "content" TEXT,
    "embedding" public.vector(1536) NOT NULL,
    "is_relevant" BOOL NOT NULL DEFAULT True,
    "session_id" UUID NOT NULL REFERENCES "sessions" ("id") ON DELETE CASCADE
);
        CREATE TABLE IF NOT EXISTS "images" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" SERIAL NOT NULL PRIMARY KEY,
    "img_base64" TEXT NOT NULL,
    "s3_url" TEXT NOT NULL,
    "is_relevant" BOOL NOT NULL DEFAULT True,
    "message_id" INT NOT NULL REFERENCES "messages" ("id") ON DELETE CASCADE
);
        CREATE TABLE IF NOT EXISTS "usages" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" SERIAL NOT NULL PRIMARY KEY,
    "usage_count" INT NOT NULL DEFAULT 1,
    "source" VARCHAR(100) NOT NULL,
    "is_message" BOOL NOT NULL DEFAULT False,
    "user_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "sessions";
        DROP TABLE IF EXISTS "messages";
        DROP TABLE IF EXISTS "images";
        DROP TABLE IF EXISTS "usages";
        """
