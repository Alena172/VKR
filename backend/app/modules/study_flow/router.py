from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.study_flow.schemas import (
    CaptureToVocabularyRequest,
    CaptureToVocabularyRequestMe,
)
from app.modules.users.repository import users_repository

router = APIRouter(prefix="/study-flow", tags=["study_flow"])


class AsyncTaskResponse(BaseModel):
    task_id: str
    status: str = "PENDING"
    message: str = "Task queued. Poll /api/v1/tasks/{task_id} for result."


@router.post("/me/capture-to-vocabulary", response_model=AsyncTaskResponse, status_code=202)
def capture_to_vocabulary_me(
    payload: CaptureToVocabularyRequestMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
    """Queue the capture-to-vocabulary pipeline for the current user.

    Returns 202 Accepted with a task_id. Poll GET /api/v1/tasks/{task_id}
    until status == SUCCESS to get the CaptureToVocabularyResponse.
    """
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    from app.tasks.vocabulary_tasks import study_flow_capture_to_vocabulary

    task = study_flow_capture_to_vocabulary.delay(
        user_id=current_user_id,
        selected_text=payload.selected_text,
        source_url=payload.source_url,
        source_sentence=payload.source_sentence,
        force_new_vocabulary_item=payload.force_new_vocabulary_item,
    )
    return AsyncTaskResponse(task_id=task.id)


@router.post("/capture-to-vocabulary", response_model=AsyncTaskResponse, status_code=202)
def capture_to_vocabulary(
    payload: CaptureToVocabularyRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
    """Queue the capture-to-vocabulary pipeline (explicit user_id variant)."""
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, target_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    from app.tasks.vocabulary_tasks import study_flow_capture_to_vocabulary

    task = study_flow_capture_to_vocabulary.delay(
        user_id=target_user_id,
        selected_text=payload.selected_text,
        source_url=payload.source_url,
        source_sentence=payload.source_sentence,
        force_new_vocabulary_item=payload.force_new_vocabulary_item,
    )
    return AsyncTaskResponse(task_id=task.id)
