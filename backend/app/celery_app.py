"""Celery application factory.

Import this module to get the configured Celery instance.
Tasks are auto-discovered from app.tasks.*
"""
from __future__ import annotations

from celery import Celery

from app.core.config import get_settings


def create_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "vkr_worker",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=[
            "app.tasks.vocabulary_tasks",
            "app.tasks.exercise_tasks",
        ],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # Keep results for 1 hour so the frontend can poll
        result_expires=3600,
        # Acknowledge tasks only after they complete (safer)
        task_acks_late=True,
        # Prefetch one task at a time per worker
        worker_prefetch_multiplier=1,
        # Retry connection to broker on startup
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery()
