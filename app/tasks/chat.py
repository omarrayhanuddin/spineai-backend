import asyncio
import random
from datetime import datetime, timezone, timedelta
from app.celery import app
from tortoise import Tortoise
from app.db.config import TORTOISE_ORM
from app.models.chat import ChatSession
from app.models.notification import Notification

# List of varied reminder messages
REMINDER_MESSAGES = [
    "It's been a week since your last recommendations. Have you tried the suggested activities yet?",
    "Hey, a week has passed! Time to check in on those recommended exercises or actions.",
    "Your weekly reminder: Have you followed up on the spine health recommendations we sent?",
    "Seven days later—any progress on the activities we recommended last time?",
    "Time flies! It's been a week—have you done the recommended spine care activities?",
    "Just checking in! It's been 7 days—how are you doing with the recommendations?",
    "A week ago, we sent some recommendations. Have you had a chance to try them out?"
]

# Send recommendations notification to users every 7th day from the date of recommendations_notified_at
@app.task
def send_recommendations_notification():
    async def async_db_operation():
        await Tortoise.init(config=TORTOISE_ORM)
        await Tortoise.generate_schemas()
        try:
            current_date = datetime.now(timezone.utc)
            seven_days_ago = current_date - timedelta(days=7)
            older_sessions = await ChatSession.filter(
                recommendations_notified_at__lte=seven_days_ago,
                recommendations_notified_at__isnull=False,
            ).select_related("user")
            older_sessions_ids = []
            for session in older_sessions:
                try:
                    # Randomly select a message from the REMINDER_MESSAGES list
                    random_message = random.choice(REMINDER_MESSAGES)
                    await Notification.create(
                        user=session.user,
                        message=random_message,
                        type="recommendations_reminder",
                        session=session
                    )
                    older_sessions_ids.append(session.id)
                except Exception as e:
                    print(f"Error creating notification for session {session.id}: {e}")
                    continue
            if older_sessions_ids:
                try:
                    await ChatSession.filter(id__in=older_sessions_ids).update(
                        recommendations_notified_at=current_date
                    )
                except Exception as e:
                    print(f"Error updating session timestamps: {e}")
                    return {
                        "status": "partial_success",
                        "error": str(e),
                        "notified_sessions": len(older_sessions_ids),
                    }
            return {"status": "success", "notified_sessions": len(older_sessions_ids)}
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {"status": "error", "error": str(e)}
        finally:
            await Tortoise.close_connections()

    # Run the async operation in the current event loop to avoid issues with Celery
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop.create_task(async_db_operation()).result()
    else:
        return loop.run_until_complete(async_db_operation())