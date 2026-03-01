"""Task status polling endpoint.

Clients submit a task_id returned by an async endpoint and poll
GET /tasks/{task_id} until status is SUCCESS or FAILURE.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.modules.auth.dependencies import get_current_user_id

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str  # PENDING | STARTED | SUCCESS | FAILURE | RETRY | REVOKED
    result: dict | list | None = None
    error: str | None = None


@router.get("/{task_id}", response_model=TaskStatusResponse)
def get_task_status(
    task_id: str,
    _current_user_id: int = Depends(get_current_user_id),
) -> TaskStatusResponse:
    """Poll the status of a background Celery task.

    Returns the task result once it reaches SUCCESS state.
    """
    from celery.result import AsyncResult

    from app.celery_app import celery_app

    result = AsyncResult(task_id, app=celery_app)
    status = result.status  # PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED

    if status == "SUCCESS":
        task_result = result.result
        if isinstance(task_result, dict):
            return TaskStatusResponse(task_id=task_id, status=status, result=task_result)
        if isinstance(task_result, list):
            return TaskStatusResponse(task_id=task_id, status=status, result=task_result)
        return TaskStatusResponse(task_id=task_id, status=status, result={"value": task_result})

    if status == "FAILURE":
        exc = result.result
        error_msg = str(exc) if exc else "Unknown error"
        return TaskStatusResponse(task_id=task_id, status=status, error=error_msg)

    # PENDING / STARTED / RETRY
    return TaskStatusResponse(task_id=task_id, status=status)
