from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init

import config
from database import engine

celery_app = Celery(
    "taskhub",
    broker=config.CELERY_BROKER_URL,
    backend=config.CELERY_RESULT_BACKEND,
    include=["workers.tasks"],
)
celery_app.conf.update(
    timezone=config.CELERY_TIMEZONE,
    enable_utc=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={
        "visibility_timeout": 3600, "socket_connect_timeout": 3, "socket_timeout": 3,
    },
    result_backend_transport_options={"visibility_timeout": 3600},
    visibility_timeout=3600,
    result_expires=86400,
    task_soft_time_limit=1500,
    task_time_limit=1800,
    task_default_queue="maintenance",
    task_routes={"taskhub.execute_job": {"queue": "heavy"}},
    beat_schedule={
        "recover-pending-jobs": {"task": "taskhub.dispatch_pending", "schedule": 30.0},
        "daily-task-reminders": {
            "task": "taskhub.schedule_reminders",
            "schedule": crontab(hour=8, minute=0),
        },
    },
)


@worker_process_init.connect
def reset_inherited_connections(**_kwargs):
    # Never share DB connections between prefork children.
    engine.dispose(close=False)
