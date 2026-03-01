"""Celery tasks for vocabulary operations.

These tasks offload slow AI calls (context definition generation,
translation) from the HTTP request cycle so the user gets an
immediate response and the heavy work happens in the background.
"""
from __future__ import annotations

import asyncio
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="vocabulary.add_word_with_ai",
    max_retries=2,
    default_retry_delay=5,
)
def add_word_with_ai(
    self,
    *,
    user_id: int,
    english_lemma: str,
    russian_translation: str,
    source_sentence: str | None,
    source_url: str | None,
) -> dict:
    """Create a vocabulary item with AI-generated context definition.

    Returns a dict that matches the VocabularyItem schema so the
    frontend can use it directly after polling.
    """
    from app.core.db import SessionLocal
    from app.modules.ai_services.service import ai_service
    from app.modules.vocabulary.repository import vocabulary_repository
    from app.modules.vocabulary.schemas import VocabularyItemCreate

    db = SessionLocal()
    try:
        context_definition_ru = ai_service.generate_context_definition(
            english_lemma=english_lemma,
            russian_translation=russian_translation,
            source_sentence=source_sentence,
        )
        item = vocabulary_repository.create(
            db,
            VocabularyItemCreate(
                user_id=user_id,
                english_lemma=english_lemma,
                russian_translation=russian_translation,
                context_definition_ru=context_definition_ru,
                source_sentence=source_sentence,
                source_url=source_url,
            ),
        )
        return {
            "id": item.id,
            "user_id": item.user_id,
            "english_lemma": item.english_lemma,
            "russian_translation": item.russian_translation,
            "context_definition_ru": item.context_definition_ru,
            "source_sentence": item.source_sentence,
            "source_url": item.source_url,
        }
    except Exception as exc:
        logger.exception("add_word_with_ai failed for user=%s lemma=%s", user_id, english_lemma)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="vocabulary.study_flow_capture_to_vocabulary",
    max_retries=2,
    default_retry_delay=5,
)
def study_flow_capture_to_vocabulary(
    self,
    *,
    user_id: int,
    selected_text: str,
    source_url: str | None,
    source_sentence: str | None,
    force_new_vocabulary_item: bool,
) -> dict:
    """Run the full study-flow capture-to-vocabulary pipeline in a worker.

    Returns a dict matching CaptureToVocabularyResponse schema.
    """
    from app.core.db import SessionLocal
    from app.modules.ai_services.contracts import TranslateWithContextRequest
    from app.modules.ai_services.service import ai_service
    from app.modules.capture.models import CaptureItemModel
    from app.modules.context_memory.repository import context_repository
    from app.modules.learning_graph.repository import learning_graph_repository
    from app.modules.users.repository import users_repository
    from app.modules.vocabulary.models import VocabularyItemModel
    from app.modules.vocabulary.repository import vocabulary_repository

    def _normalize_english_lemma(text: str) -> str:
        return text.strip().split()[0].lower()

    def _normalize_translation(text: str) -> str:
        value = text.strip()
        if value.startswith("[RU]"):
            value = value.replace("[RU]", "", 1).strip()
        return value or "перевод не найден"

    db = SessionLocal()
    try:
        user = users_repository.get_by_id(db, user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")

        capture_row = CaptureItemModel(
            user_id=user_id,
            selected_text=selected_text,
            source_url=source_url,
            source_sentence=source_sentence,
        )
        db.add(capture_row)
        db.flush()

        english_lemma = _normalize_english_lemma(selected_text)

        # Run async AI calls in a new event loop inside the worker
        async def _run_ai() -> tuple[str, str]:
            ai_response = await ai_service.translate_with_context_async(
                TranslateWithContextRequest(
                    text=english_lemma,
                    cefr_level=user.cefr_level,
                    source_context=source_sentence,
                )
            )
            russian_translation = _normalize_translation(ai_response.translated_text)
            context_definition_ru = await ai_service.generate_context_definition_async(
                english_lemma=english_lemma,
                russian_translation=russian_translation,
                source_sentence=source_sentence,
                cefr_level=user.cefr_level,
            )
            return russian_translation, context_definition_ru

        russian_translation, context_definition_ru = asyncio.run(_run_ai())

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

        return {
            "capture": {
                "id": capture_row.id,
                "user_id": capture_row.user_id,
                "selected_text": capture_row.selected_text,
                "source_url": capture_row.source_url,
                "source_sentence": capture_row.source_sentence,
            },
            "vocabulary": {
                "id": vocabulary_row.id,
                "user_id": vocabulary_row.user_id,
                "english_lemma": vocabulary_row.english_lemma,
                "russian_translation": vocabulary_row.russian_translation,
                "context_definition_ru": vocabulary_row.context_definition_ru,
                "source_sentence": vocabulary_row.source_sentence,
                "source_url": vocabulary_row.source_url,
            },
            "translation_note": "AI translation used (worker)",
            "created_new_vocabulary_item": created_new,
            "queued_for_review": progress is not None,
        }
    except Exception as exc:
        db.rollback()
        logger.exception(
            "study_flow_capture_to_vocabulary failed for user=%s text=%s",
            user_id,
            selected_text,
        )
        raise self.retry(exc=exc)
    finally:
        db.close()
