from tortoise import BaseDBAsyncClient


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "treatment_categories" (
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "session_id" UUID NOT NULL REFERENCES "sessions" ("id") ON DELETE CASCADE
);
        CREATE TABLE IF NOT EXISTS "weekly_plans" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(255) NOT NULL,
    "description" TEXT NOT NULL,
    "start_date" DATE NOT NULL,
    "end_date" DATE NOT NULL,
    "category_id" INT NOT NULL REFERENCES "treatment_categories" ("id") ON DELETE CASCADE
);
    CREATE TABLE IF NOT EXISTS "tasks" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "title" VARCHAR(255) NOT NULL,
    "description" TEXT NOT NULL,
    "date" DATE NOT NULL,
    "status" VARCHAR(50) NOT NULL DEFAULT 'pending',
    "weekly_plan_id" INT NOT NULL REFERENCES "weekly_plans" ("id") ON DELETE CASCADE
);
COMMENT ON COLUMN "weekly_plans"."name" IS 'e.g., ''Week-1''';
COMMENT ON COLUMN "tasks"."status" IS 'e.g., ''completed'', ''pending'', ''in progress''';
COMMENT ON COLUMN "treatment_categories"."name" IS 'e.g., ''exercise'', ''cold therapy''';
"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "weekly_plans";
        DROP TABLE IF EXISTS "tasks";
        DROP TABLE IF EXISTS "treatment_categories";"""
