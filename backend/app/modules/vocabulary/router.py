from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.ai_services.service import ai_service
from app.modules.auth.dependencies import get_current_user_id
from app.modules.users.repository import users_repository
from app.modules.vocabulary.repository import vocabulary_repository
from app.modules.vocabulary.schemas import (
    VocabularyItem,
    VocabularyItemCreate,
    VocabularyItemCreateMe,
    VocabularyItemUpdateMe,
)

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


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


@router.post("/me", response_model=VocabularyItem)
def add_my_item(
    payload: VocabularyItemCreateMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> VocabularyItem:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    english_lemma = payload.english_lemma.strip().lower()
    russian_translation = payload.russian_translation.strip()
    source_sentence = payload.source_sentence.strip() if payload.source_sentence else None
    context_definition_ru = ai_service.generate_context_definition(
        english_lemma=english_lemma,
        russian_translation=russian_translation,
        source_sentence=source_sentence,
        cefr_level=user.cefr_level,
    )
    return vocabulary_repository.create(
        db,
        VocabularyItemCreate(
            user_id=current_user_id,
            english_lemma=english_lemma,
            russian_translation=russian_translation,
            context_definition_ru=context_definition_ru,
            source_sentence=source_sentence,
            source_url=payload.source_url.strip() if payload.source_url else None,
        ),
    )


@router.post("", response_model=VocabularyItem)
def add_item(
    payload: VocabularyItemCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> VocabularyItem:
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, target_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    english_lemma = payload.english_lemma.strip().lower()
    russian_translation = payload.russian_translation.strip()
    source_sentence = payload.source_sentence.strip() if payload.source_sentence else None
    context_definition_ru = ai_service.generate_context_definition(
        english_lemma=english_lemma,
        russian_translation=russian_translation,
        source_sentence=source_sentence,
        cefr_level=user.cefr_level,
    )
    return vocabulary_repository.create(
        db,
        payload.model_copy(
            update={
                "user_id": target_user_id,
                "english_lemma": english_lemma,
                "russian_translation": russian_translation,
                "context_definition_ru": context_definition_ru,
                "source_sentence": source_sentence,
                "source_url": payload.source_url.strip() if payload.source_url else None,
            }
        ),
    )


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
