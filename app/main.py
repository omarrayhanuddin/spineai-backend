from tortoise import Tortoise
from fastapi import FastAPI
from app.db.config import init_db
from app.api.v1 import user, chat, payment, notification, transcribe, treatment_plan, admin
from contextlib import asynccontextmanager
from httpx import AsyncClient as HttpxAsyncClient
from app.core.config import settings
from openai import AsyncClient as OpenAiAsyncClient
from fastapi.middleware.cors import CORSMiddleware
from stripe import StripeClient
from pathlib import Path
import aiofiles
import json
import logging
import subprocess
import sys

logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


async def run_aerich_upgrade():
    try:
        logger.info("[AERICH] Running aerich upgrade...")
        result = subprocess.run(
            [sys.executable, "-m", "aerich", "upgrade"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info(f"[AERICH] Upgrade successful:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        logger.error(f"[AERICH] Upgrade failed:\n{e.stderr}")
        raise RuntimeError("Aerich upgrade failed")
    except FileNotFoundError:
        logger.critical(
            "[AERICH] 'aerich' command not found. Ensure it's installed and in PATH."
        )
        raise RuntimeError("Aerich command not found.")
    except Exception as e:
        logger.exception(f"[AERICH] An unexpected error occurred during upgrade: {e}")
        raise


async def create_or_update_plans_from_file(filepath: Path = "stage_plans.json"):
    from app.models.payment import Plan

    if settings.APP_ENV == "production":
        filepath = Path("production_plans.json")
        logger.info(f"Using production plans file: {filepath}")
    else:
        filepath = Path("stage_plans.json")
        logger.info(f"Using staging plans file: {filepath}")

    if not filepath.exists():
        logger.critical(
            f"Required plans file '{filepath}' not found for current environment. Application cannot start."
        )
        raise FileNotFoundError(f"Required plans file '{filepath}' not found.")

    try:
        async with aiofiles.open(filepath, mode="r") as f:
            content = await f.read()
            plans = json.loads(content)
        logger.info(f"Successfully loaded plans from '{filepath}'.")
    except json.JSONDecodeError as e:
        logger.critical(f"Error decoding JSON from plans file '{filepath}': {e}")
        raise ValueError(f"Invalid JSON in plans file '{filepath}'.")
    except Exception as e:
        logger.exception(
            f"An unexpected error occurred while reading plans file '{filepath}': {e}"
        )
        raise
    await Plan.all().delete()
    for plan_data in plans:
        try:
            plan, created = await Plan.get_or_create(
                name=plan_data["name"], defaults=plan_data
            )
            if not created:
                await plan.update_from_dict(plan_data)
                await plan.save()
                logger.info(f"Updated existing plan: {plan.name}")
            else:
                logger.info(f"Created new plan: {plan.name}")
        except Exception as e:
            logger.error(
                f"Failed to create or update plan '{plan_data.get('name', 'UNKNOWN')}': {e}"
            )


async def setup_pgvector_hnsw():
    try:
        conn = Tortoise.get_connection("default")
        await conn.execute_script("CREATE EXTENSION IF NOT EXISTS vector;")
        logger.info("Ensured 'vector' extension is enabled for PostgreSQL.")
        await conn.execute_script(
            """
            CREATE INDEX IF NOT EXISTS messages_embedding_hnsw_idx
            ON messages
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
            """
        )
        logger.info(
            "Ensured HNSW index on 'messages.embedding' is created."
        )
    except Exception as e:
        logger.critical(f"Failed to set up pgvector HNSW index: {e}")
        raise

async def update_user_plan():
    from app.models.user import User
    await User.all().update(current_plan="price_1Rn2npFjPe0daNEdBtVYGnAR")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles application startup and shutdown events."""
    app.state.httpx_client = None
    try:
        logger.info("Application lifespan startup initiated.")
        # await run_aerich_upgrade()
        await setup_pgvector_hnsw()
        await create_or_update_plans_from_file()
        # await update_user_plan()

        app.state.openai_client = OpenAiAsyncClient(api_key=settings.OPENAI_API_KEY)
        app.state.httpx_client = HttpxAsyncClient()
        app.state.stripe_client = StripeClient(api_key=settings.STRIPE_API_KEY)

        logger.info("External clients (OpenAI, HTTPX, Stripe) initialized.")

        yield
    except Exception as e:
        logger.critical(f"Error during application startup: {e}", exc_info=True)
        raise
    finally:
        if app.state.httpx_client:
            await app.state.httpx_client.aclose()
            logger.info("HTTPX client closed.")
        logger.info("Application lifespan shutdown completed.")


app = FastAPI(title="SpineAi Backend APIs", lifespan=lifespan)

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS middleware configured.")

init_db(app)
logger.info("Database initialized with Tortoise ORM.")

app.include_router(user.router)
app.include_router(chat.router)
app.include_router(payment.router)
app.include_router(notification.router)
app.include_router(transcribe.router)
app.include_router(treatment_plan.router)
app.include_router(admin.router)
# app.include_router(feedback.router)
logger.info("API routers included: user, chat, payment, feedback.")