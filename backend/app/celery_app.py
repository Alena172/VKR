"""Celery application factory with a lightweight local fallback.

Import this module to get the configured Celery instance.
Tasks are auto-discovered from app.tasks.* when Celery is installed.
In test environments without Celery, tasks still expose `.delay(...)`
and store in-memory results that can be polled through `/tasks/{task_id}`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.core.config import get_settings

_LOCAL_TASK_RESULTS: dict[str, dict[str, Any]] = {}
CELERY_AVAILABLE = True

try:
    from celery import Celery
except ModuleNotFoundError:
    CELERY_AVAILABLE = False
    Celery = None  # type: ignore[assignment]


@dataclass
class LocalTaskResult:
    id: str


class LocalTaskContext:
    def retry(self, *, exc: Exception, **_: Any) -> None:
        raise exc


class LocalTaskWrapper:
    def __init__(self, fn, *, bind: bool) -> None:
        self._fn = fn
        self._bind = bind

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if self._bind:
            return self._fn(LocalTaskContext(), *args, **kwargs)
        return self._fn(*args, **kwargs)

    def delay(self, *args: Any, **kwargs: Any) -> LocalTaskResult:
        task_id = str(uuid.uuid4())
        _LOCAL_TASK_RESULTS[task_id] = {"status": "STARTED", "result": None, "error": None}
        try:
            result = self(*args, **kwargs)
            _LOCAL_TASK_RESULTS[task_id] = {"status": "SUCCESS", "result": result, "error": None}
        except Exception as exc:
            _LOCAL_TASK_RESULTS[task_id] = {"status": "FAILURE", "result": None, "error": str(exc)}
        return LocalTaskResult(id=task_id)


class LocalCeleryApp:
    def task(self, *decorator_args: Any, **decorator_kwargs: Any):
        bind = bool(decorator_kwargs.get("bind", False))

        def decorator(fn):
            return LocalTaskWrapper(fn, bind=bind)

        return decorator


def create_celery():
    if not CELERY_AVAILABLE:
        return LocalCeleryApp()

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
        result_expires=3600,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
    )
    return app


celery_app = create_celery()
