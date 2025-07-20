import asyncio
import random
from datetime import datetime, timezone, timedelta
from app.celery import app
from tortoise import Tortoise
from app.db.config import TORTOISE_ORM
from app.models.chat import ChatSession
from app.models.notification import Notification
from app.models.treatment_plan import TreatmentCategory, WeeklyPlan, Task

# List of varied reminder messages
REMINDER_MESSAGES = [
    "It's been a week since your last recommendations. Have you tried the suggested activities yet?",
    "Hey, a week has passed! Time to check in on those recommended exercises or actions.",
    "Your weekly reminder: Have you followed up on the spine health recommendations we sent?",
    "Seven days later—any progress on the activities we recommended last time?",
    "Time flies! It's been a week—have you done the recommended spine care activities?",
    "Just checking in! It's been 7 days—how are you doing with the recommendations?",
    "A week ago, we sent some recommendations. Have you had a chance to try them out?",
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
                        session=session,
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


@app.task
def create_treatment_plan_from_ai_response(ai_response_json: dict):
    """
    Celery task to parse an AI response (JSON) and create a treatment plan
    in the database.

    Args:
        ai_response_json (dict): The JSON response from the AI containing
        the "treatment" structure.
    """

    async def async_db_operation():
        await Tortoise.init(config=TORTOISE_ORM)
        await Tortoise.generate_schemas()

        try:
            treatment_data = ai_response_json.get("treatment")
            if not treatment_data:
                return {
                    "status": "error",
                    "message": "AI response missing 'treatment' key.",
                }

            for category_name, weekly_plans_data in treatment_data.items():
                category, created = await TreatmentCategory.update_or_create(
                    name=category_name, defaults={"name": category_name}
                )
                print(
                    f"Category '{category_name}' {'created' if created else 'found'}."
                )

                for weekly_plan_item in weekly_plans_data:
                    # Parse dates
                    start_date = datetime.strptime(
                        weekly_plan_item["startDate"], "%Y-%m-%d"
                    ).date()
                    end_date = datetime.strptime(
                        weekly_plan_item["endDate"], "%Y-%m-%d"
                    ).date()

                    # Create or update the WeeklyPlan
                    weekly_plan, created_weekly = await WeeklyPlan.update_or_create(
                        name=weekly_plan_item["name"],
                        category=category,
                        defaults={
                            "description": weekly_plan_item["description"],
                            "start_date": start_date,
                            "end_date": end_date,
                            "category": category,
                        },
                    )
                    print(
                        f"  Weekly Plan '{weekly_plan.name}' for '{category_name}' {'created' if created_weekly else 'found'}."
                    )

                    for task_item in weekly_plan_item["task"]:
                        # Parse task date
                        task_date = datetime.strptime(
                            task_item["date"], "%Y-%m-%d"
                        ).date()
                        task, created_task = await Task.update_or_create(
                            title=task_item["title"],
                            weekly_plan=weekly_plan,
                            defaults={
                                "description": task_item["description"],
                                "date": task_date,
                                "status": task_item["status"],
                                "weekly_plan": weekly_plan,
                            },
                        )
                        print(
                            f"Task '{task.title}' {'created' if created_task else 'found'}."
                        )

            return {
                "status": "success",
                "message": "Treatment plan successfully processed and saved.",
            }
        except Exception as e:
            print(f"Error processing AI response: {e}")
            return {
                "status": "error",
                "message": f"Failed to process treatment plan: {e}",
            }
        finally:
            await Tortoise.close_connections()

    # Run the async operation in the current event loop
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop.create_task(async_db_operation()).result()
    else:
        return loop.run_until_complete(async_db_operation())
