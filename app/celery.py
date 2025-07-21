from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from datetime import timedelta
# from datetime import timedelta # Import timedelta

def create_celery():
    celery_app = Celery(
        __name__,
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
        include=['app.tasks.chat']
    )
    
    # Celery configuration
    celery_app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        # Celery Beat schedule
        beat_schedule={
            'send-recommendations-notification-once-a-day': {
                'task': 'app.tasks.chat.send_recommendations_notification',
                # 'schedule': crontab(hour='14', minute=0),
                # 'schedule': crontab(minute=0),
                'schedule': timedelta(seconds=5),
            },
            'send-treatment-notification-once-a-day': {
                'task': 'app.tasks.chat.send_daily_treatment_notification',
                'schedule': crontab(hour='12', minute=0),
                # 'schedule': crontab(minute=0),
                # 'schedule': timedelta(seconds=15),
            },
            'create-treatment-plan-end-of-day': {
                'task': 'app.tasks.chat.create_treatment_plan_from_ai_response',
                'schedule': crontab(hour='22', minute=0),
                # 'schedule': crontab(minute=0),
                # 'schedule': timedelta(seconds=20),
            },
        }
    )
    
    return celery_app

app = create_celery()