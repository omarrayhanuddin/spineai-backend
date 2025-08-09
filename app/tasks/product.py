from app.celery import app
from app.db.config import TORTOISE_ORM
from app.core.config import settings
from app.models.chat import ChatSession
from tortoise import Tortoise
from app.utils.helpers import generate_product_recommendation_prompt
from openai import AsyncClient
import json
import asyncio

async def async_db_get_ai_recommendation(session_id):
    print("Session ID:", session_id)
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
    openai_client = AsyncClient(api_key=settings.OPENAI_API_KEY)
    try:
        session = await ChatSession.get_or_none(id=session_id)
        if not session:
            raise ValueError("Session not found")
        message = generate_product_recommendation_prompt(
            findings=session.findings,
        )
        response = await openai_client.chat.completions.create(
            model="gpt-5",
            messages=message,
            response_format={"type": "json_object"},
        )
        result = response.choices[0].message.content
        ai_response = json.loads(result)
        ai_recommendations_tags = ai_response.get("product_tags", [])
        session.suggested_product_tags = ai_recommendations_tags
        await session.save()
        print("AI Recommendations Tags:", ai_recommendations_tags)
    except Exception as e:
        print(f"Error processing AI response: {e}")
    finally:
        await Tortoise.close_connections()
        await openai_client.close()

@app.task
def get_ai_tags_per_session(session_id):
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop.create_task(async_db_get_ai_recommendation(session_id)).result()
    else:
        return loop.run_until_complete(async_db_get_ai_recommendation(session_id))
