import asyncio
import random
import json
from datetime import datetime, timezone, timedelta
from app.celery import app
from tortoise import Tortoise
from app.db.config import TORTOISE_ORM
from app.models.chat import ChatSession
from app.models.notification import Notification
from app.models.treatment_plan import TreatmentCategory, WeeklyPlan, Task
from app.models.user import User
from app.core.config import settings
from openai import AsyncClient
from app.utils.helpers import generate_treatment_plan_prompt
from app.services.email_service import send_email
from datetime import date

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
TREATMENT_PLAN_NOTIFICATION_TITLES = [
    "Your Daily Plan is Ready!",
    "Today's Treatment Tasks",
    "Time for Your Spine Plan!",
    "Daily SpineAi Tasks",
    "Your Plan for Today",
    "Get Started on Your Plan",
    "Treatment Plan Update",
    "Today's Wellness Tasks",
    "Your Daily Spine Health",
    "Action Your Daily Plan",
]


# Send recommendations notification to users every 7th day from the date of recommendations_notified_at
async def async_db_operation_for_recommendations_notify():
    await Tortoise.init(config=TORTOISE_ORM)
    await Tortoise.generate_schemas()
    try:
        current_date = datetime.now(timezone.utc)
        seven_days_ago = current_date - timedelta(days=7)
        older_sessions = await ChatSession.filter(
            recommendations_notified_at__lte=seven_days_ago,
            recommendations_notified_at__isnull=False,
            user__current_plan__isnull=False,
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
                context = {
                    "user_name": session.user.full_name,
                    "body": random_message,
                    "link": f"{settings.SITE_DOMIN}/dashboard/chat/{session.id}",
                }
                await send_email(
                    recipient=session.user.email,
                    subject=f"Online Spine Health: {random_message}",
                    context=context,
                    template_name="recommendation_reminder.html",
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


@app.task
def send_recommendations_notification():

    # Run the async operation in the current event loop to avoid issues with Celery
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop.create_task(
            async_db_operation_for_recommendations_notify()
        ).result()
    else:
        return loop.run_until_complete(async_db_operation_for_recommendations_notify())


async def async_db_operation_for_treatment_notify():
    # await Tortoise.init(config=TORTOISE_ORM)
    # await Tortoise.generate_schemas()
    try:
        current_date = datetime.now(timezone.utc)
        pro_users = await User.filter(current_plan=settings.TREATMENT_PLAN_PRICE_ID)
        for user in pro_users:
            dail_tasks = (
                await Task.filter(
                    weekly_plan__category__session__user=user, date=current_date
                )
                .limit(5)
                .values("id", "title", "description")
            )
            if not dail_tasks:
                continue
            random_message = random.choice(TREATMENT_PLAN_NOTIFICATION_TITLES)
            await Notification.create(
                user=user,
                message=random_message,
                type="daily_treatment_reminder",
            )
            context = {
                "user_name": user.full_name,
                "today_date": current_date.strftime("%Y-%m-%d"),
                "tasks": dail_tasks,
                "link": f"{settings.SITE_DOMIN}/dashboard/treatments?date={current_date.strftime('%Y-%m-%d')}",
            }
            await send_email(
                recipient=user.email,
                subject=f"Online Spine Health: {random_message}",
                context=context,
                template_name="treatment_reminder.html",
            )
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {"status": "error", "error": str(e)}
    finally:
        await Tortoise.close_connections()


@app.task
def send_daily_treatment_notification():

    # Run the async operation in the current event loop to avoid issues with Celery
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop.create_task(async_db_operation_for_treatment_notify()).result()
    else:
        return loop.run_until_complete(async_db_operation_for_treatment_notify())


@app.task
def create_treatment_plan_from_ai_response():
    """
    Celery task to parse an AI response (JSON) and create a treatment plan
    in the database.

    Args:
        ai_response_json (dict): The JSON response from the AI containing
        the "treatment" structure.
    """

    async def async_db_operation():
        try:
            await Tortoise.init(config=TORTOISE_ORM)
            await Tortoise.generate_schemas()
            print("Tortoise initialized")
            openai_client = AsyncClient(api_key=settings.OPENAI_API_KEY)
            treatment_sessions = await ChatSession.filter(
                is_diagnosed=True,
                user__current_plan=settings.TREATMENT_PLAN_PRICE_ID,
                findings__isnull=False,
                treatment_plans__isnull=True,
            )
            print("Found {} treatment sessions".format(len(treatment_sessions)))

            for session in treatment_sessions:
                message = generate_treatment_plan_prompt(
                    findings=session.findings,
                    recommendations=session.recommendations,
                    date=datetime.now().strftime("%Y-%m-%d"),
                )
                response = await openai_client.chat.completions.create(
                    model="gpt-4.1-2025-04-14",
                    messages=message,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
                result = response.choices[0].message.content
                treatment_data = json.loads(result)
                for category_name, weekly_plans_data in treatment_data[
                    "treatment"
                ].items():
                    treatment_category, _ = await TreatmentCategory.get_or_create(
                        name=category_name, session=session
                    )
                    for weekly_plan_data in weekly_plans_data:
                        weekly_plan, _ = await WeeklyPlan.get_or_create(
                            name=weekly_plan_data["name"],
                            category=treatment_category,
                            defaults={
                                "description": weekly_plan_data["description"],
                                "start_date": date.fromisoformat(
                                    weekly_plan_data["startDate"]
                                ),
                                "end_date": date.fromisoformat(
                                    weekly_plan_data["endDate"]
                                ),
                            },
                        )
                        for task_data in weekly_plan_data["task"]:
                            await Task.get_or_create(
                                title=task_data["title"],
                                date=date.fromisoformat(task_data["date"]),
                                weekly_plan=weekly_plan,
                                defaults={
                                    "description": task_data["description"],
                                    "status": task_data["status"],
                                },
                            )
        except Exception as e:
            print(f"Error processing AI response: {e}")
        finally:
            await Tortoise.close_connections()

    # Run the async operation in the current event loop
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop.create_task(async_db_operation()).result()
    else:
        return loop.run_until_complete(async_db_operation())
