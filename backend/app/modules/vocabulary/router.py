from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.users.repository import users_repository
from app.modules.vocabulary.repository import vocabulary_repository
from app.modules.vocabulary.schemas import (
    VocabularyFromCaptureRequest,
    VocabularyFromCaptureRequestMe,
    VocabularyItem,
    VocabularyItemCreate,
    VocabularyItemCreateMe,
    VocabularyItemUpdateMe,
)

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


class AsyncTaskResponse(BaseModel):
    task_id: str
    status: str = "PENDING"
    message: str = "Task queued. Poll /api/v1/tasks/{task_id} for result."


@router.get("/me", response_model=list[VocabularyItem])
def list_my_items(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[VocabularyItem]:
    return vocabulary_repository.list_items(db, user_id=current_user_id)


@router.get("", response_model=list[VocabularyItem])
def list_items(
    user_id: int | None = Query(default=None, ge=1),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[VocabularyItem]:
    if user_id is not None and user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return vocabulary_repository.list_items(db, user_id=user_id or current_user_id)


@router.post("/me", response_model=AsyncTaskResponse, status_code=202)
def add_my_item(
    payload: VocabularyItemCreateMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
    """Queue vocabulary item creation with AI context definition generation.

    Returns 202 Accepted with a task_id. Poll GET /api/v1/tasks/{task_id}
    until status == SUCCESS to get the created VocabularyItem.
    """
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    from app.tasks.vocabulary_tasks import add_word_with_ai

    english_lemma = payload.english_lemma.strip().lower()
    russian_translation = payload.russian_translation.strip()
    source_sentence = payload.source_sentence.strip() if payload.source_sentence else None
    source_url = payload.source_url.strip() if payload.source_url else None

    task = add_word_with_ai.delay(
        user_id=current_user_id,
        english_lemma=english_lemma,
        russian_translation=russian_translation,
        source_sentence=source_sentence,
        source_url=source_url,
    )
    return AsyncTaskResponse(task_id=task.id)


@router.post("", response_model=AsyncTaskResponse, status_code=202)
def add_item(
    payload: VocabularyItemCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
    """Queue vocabulary item creation (admin/explicit user_id variant)."""
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, target_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    from app.tasks.vocabulary_tasks import add_word_with_ai

    english_lemma = payload.english_lemma.strip().lower()
    russian_translation = payload.russian_translation.strip()
    source_sentence = payload.source_sentence.strip() if payload.source_sentence else None
    source_url = payload.source_url.strip() if payload.source_url else None

    task = add_word_with_ai.delay(
        user_id=target_user_id,
        english_lemma=english_lemma,
        russian_translation=russian_translation,
        source_sentence=source_sentence,
        source_url=source_url,
    )
    return AsyncTaskResponse(task_id=task.id)


@router.post("/me/from-capture", response_model=AsyncTaskResponse, status_code=202)
def add_my_item_from_capture(
    payload: VocabularyFromCaptureRequestMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
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


@router.post("/from-capture", response_model=AsyncTaskResponse, status_code=202)
def add_item_from_capture(
    payload: VocabularyFromCaptureRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> AsyncTaskResponse:
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


@router.put("/me/{item_id}", response_model=VocabularyItem)
def update_my_item(
    item_id: int,
    payload: VocabularyItemUpdateMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> VocabularyItem:
    item = vocabulary_repository.get_by_id_for_user(db, item_id=item_id, user_id=current_user_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    return vocabulary_repository.update(
        db,
        item,
        english_lemma=payload.english_lemma,
        russian_translation=payload.russian_translation,
        source_sentence=payload.source_sentence,
        source_url=payload.source_url,
    )


@router.delete("/me/{item_id}")
def delete_my_item(
    item_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    item = vocabulary_repository.get_by_id_for_user(db, item_id=item_id, user_id=current_user_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Vocabulary item not found")
    vocabulary_repository.delete(db, item)
    return {"deleted": True}
