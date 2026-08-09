from celery import Celery

from app.core.config import settings


celery_app = Celery("agent_eval", broker=settings.RABBITMQ_URL, backend=settings.REDIS_URL, include=["app.worker.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
    task_routes={
        "app.worker.tasks.build_submission_image": {"queue": "build"},
        "app.worker.tasks.*": {"queue": "evaluation"},
    },
    task_annotations={
        "app.worker.tasks.build_submission_image": {"time_limit": 960, "soft_time_limit": 930},
    },
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
