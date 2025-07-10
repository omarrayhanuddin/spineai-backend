from celery import Celery
from celery.schedules import crontab
from app.core.config import settings
from datetime import timedelta # Import timedelta

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
            'send-recommendations-notification-hourly': {
                'task': 'app.tasks.chat.send_recommendations_notification',
                'schedule': crontab(minute=0),
                # 'schedule': timedelta(seconds=5),
            },
        }
    )
    
    return celery_app

app = create_celery()