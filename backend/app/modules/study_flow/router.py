from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.ai_services.contracts import TranslateWithContextRequest
from app.modules.ai_services.service import (
    TranslationProviderUnavailableError,
    ai_service,
)
from app.modules.capture.models import CaptureItemModel
from app.modules.capture.schemas import CaptureItem
from app.modules.context_memory.repository import context_repository
from app.modules.learning_graph.repository import learning_graph_repository
from app.modules.study_flow.schemas import (
    CaptureToVocabularyRequest,
    CaptureToVocabularyRequestMe,
    CaptureToVocabularyResponse,
)
from app.modules.users.repository import users_repository
from app.modules.vocabulary.models import VocabularyItemModel
from app.modules.vocabulary.repository import vocabulary_repository
from app.modules.vocabulary.schemas import VocabularyItem

router = APIRouter(prefix="/study-flow", tags=["study_flow"])


def _normalize_english_lemma(text: str) -> str:
    # Keep first token as lemma candidate for extension-first workflow.
    return text.strip().split()[0].lower()


def _normalize_translation(text: str) -> str:
    value = text.strip()
    if value.startswith("[RU]"):
        value = value.replace("[RU]", "", 1).strip()
    return value or "перевод не найден"


async def _capture_to_vocabulary_for_user(
    *,
    user_id: int,
    selected_text: str,
    source_url: str | None,
    source_sentence: str | None,
    force_new_vocabulary_item: bool,
    db: Session,
) -> CaptureToVocabularyResponse:
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    capture_row = CaptureItemModel(
        user_id=user_id,
        selected_text=selected_text,
        source_url=source_url,
        source_sentence=source_sentence,
    )
    db.add(capture_row)
    db.flush()

    english_lemma = _normalize_english_lemma(selected_text)

    try:
        ai_response = await ai_service.translate_with_context_async(
            TranslateWithContextRequest(
                text=english_lemma,
                cefr_level=user.cefr_level,
                source_context=source_sentence,
            )
        )
    except TranslationProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    russian_translation = _normalize_translation(ai_response.translated_text)
    context_definition_ru = await ai_service.generate_context_definition_async(
        english_lemma=english_lemma,
        russian_translation=russian_translation,
        source_sentence=source_sentence,
        cefr_level=user.cefr_level,
    )

    existing = vocabulary_repository.get_latest_by_lemma(
        db,
        user_id=user_id,
        english_lemma=english_lemma,
    )
    created_new = existing is None or force_new_vocabulary_item

    if created_new:
        vocabulary_row = VocabularyItemModel(
            user_id=user_id,
            english_lemma=english_lemma,
            russian_translation=russian_translation,
            context_definition_ru=context_definition_ru,
            source_sentence=source_sentence,
            source_url=source_url,
        )
        db.add(vocabulary_row)
        db.flush()
    else:
        vocabulary_row = existing

    progress = context_repository.ensure_word_progress(db, user_id=user_id, word=english_lemma)
    learning_graph_repository.semantic_upsert(
        db,
        user_id=user_id,
        english_lemma=english_lemma,
        russian_translation=russian_translation,
        context_definition_ru=context_definition_ru,
        source_sentence=source_sentence,
        source_url=source_url,
        vocabulary_item_id=vocabulary_row.id,
    )
    db.commit()

    db.refresh(capture_row)
    if created_new:
        db.refresh(vocabulary_row)

    return CaptureToVocabularyResponse(
        capture=CaptureItem.model_validate(capture_row),
        vocabulary=VocabularyItem.model_validate(vocabulary_row),
        translation_note=f"AI translation used ({ai_response.provider_note})",
        created_new_vocabulary_item=created_new,
        queued_for_review=progress is not None,
    )


@router.post("/me/capture-to-vocabulary", response_model=CaptureToVocabularyResponse)
async def capture_to_vocabulary_me(
    payload: CaptureToVocabularyRequestMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CaptureToVocabularyResponse:
    return await _capture_to_vocabulary_for_user(
        user_id=current_user_id,
        selected_text=payload.selected_text,
        source_url=payload.source_url,
        source_sentence=payload.source_sentence,
        force_new_vocabulary_item=payload.force_new_vocabulary_item,
        db=db,
    )


@router.post("/capture-to-vocabulary", response_model=CaptureToVocabularyResponse)
async def capture_to_vocabulary(
    payload: CaptureToVocabularyRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CaptureToVocabularyResponse:
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await _capture_to_vocabulary_for_user(
        user_id=target_user_id,
        selected_text=payload.selected_text,
        source_url=payload.source_url,
        source_sentence=payload.source_sentence,
        force_new_vocabulary_item=payload.force_new_vocabulary_item,
        db=db,
    )
