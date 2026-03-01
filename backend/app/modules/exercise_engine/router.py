from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.exercise_engine.schemas import (
    ExerciseGenerateRequest,
    ExerciseGenerateRequestMe,
)
from app.modules.users.repository import users_repository

router = APIRouter(prefix="/exercises", tags=["exercise_engine"])


class AsyncTaskResponse(BaseModel):
    task_id: str
    status: str = "PENDING"
    message: str = "Task queued. Poll /api/v1/tasks/{task_id} for result."


@router.post("/me/generate", response_model=AsyncTaskResponse, status_code=202)
def generate_me(
    payload: ExerciseGenerateRequestMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
    """Queue exercise generation for the current user.

    Returns 202 Accepted with a task_id. Poll GET /api/v1/tasks/{task_id}
    until status == SUCCESS to get ExerciseGenerateResponse.
    """
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    from app.tasks.exercise_tasks import generate_exercises_for_user

    task = generate_exercises_for_user.delay(
        user_id=current_user_id,
        vocabulary_ids=payload.vocabulary_ids or [],
        size=payload.size,
        mode=payload.mode,
    )
    return AsyncTaskResponse(task_id=task.id)


@router.post("/generate", response_model=AsyncTaskResponse, status_code=202)
def generate(
    payload: ExerciseGenerateRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
    """Queue exercise generation (explicit user_id variant)."""
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, target_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    from app.tasks.exercise_tasks import generate_exercises_for_user

    task = generate_exercises_for_user.delay(
        user_id=target_user_id,
        vocabulary_ids=payload.vocabulary_ids or [],
        size=payload.size,
        mode=payload.mode,
    )
    return AsyncTaskResponse(task_id=task.id)
