"""Celery tasks for exercise generation.

Offloads AI exercise generation from the HTTP request cycle.
"""
from __future__ import annotations

import asyncio
import logging
import secrets

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="exercises.generate_for_user",
    max_retries=1,
    default_retry_delay=3,
)
def generate_exercises_for_user(
    self,
    *,
    user_id: int,
    vocabulary_ids: list[int],
    size: int,
    mode: str,
) -> dict:
    """Generate exercises for a user and return them as a serialisable dict.

    The result matches ExerciseGenerateResponse schema.
    """
    from app.core.db import SessionLocal
    from app.modules.ai_services.contracts import ExerciseSeed, GenerateExercisesRequest
    from app.modules.ai_services.service import TranslationProviderUnavailableError, ai_service
    from app.modules.context_memory.repository import context_repository
    from app.modules.learning_graph.repository import learning_graph_repository
    from app.modules.users.repository import users_repository
    from app.modules.vocabulary.repository import vocabulary_repository

    def _dedupe_vocabulary_by_lemma(vocabulary_items):
        deduped: dict = {}
        for item in vocabulary_items:
            key = item.english_lemma.strip().lower()
            if not key or key in deduped:
                continue
            deduped[key] = item
        return list(deduped.values())

    db = SessionLocal()
    try:
        user = users_repository.get_by_id(db, user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")

        vocabulary_items = vocabulary_repository.list_items(db, user_id=user_id)
        if vocabulary_ids:
            allowed = set(vocabulary_ids)
            vocabulary_items = [item for item in vocabulary_items if item.id in allowed]
        vocabulary_items = _dedupe_vocabulary_by_lemma(vocabulary_items)

        if not vocabulary_items:
            raise ValueError("Vocabulary is empty. Add words before generating exercises.")

        if mode == "word_definition_match":
            unique_lemmas = {item.english_lemma.strip().lower() for item in vocabulary_items if item.english_lemma}
            if len(unique_lemmas) < 4:
                raise ValueError("Need at least 4 different words in vocabulary for definition matching.")

        context = context_repository.get_by_user_id(db, user_id)
        cefr_level = context.cefr_level if context is not None else user.cefr_level

        anchors_used_count = 0
        seeds: list[ExerciseSeed] = []
        for item in vocabulary_items:
            source_sentence = item.source_sentence
            anchors = learning_graph_repository.list_anchors(
                db,
                user_id=user_id,
                english_lemma=item.english_lemma,
                limit=3,
            )
            if anchors:
                anchor_words = [anchor.english_lemma for anchor in anchors if anchor.english_lemma]
                if anchor_words:
                    anchors_used_count += 1
                    anchor_hint = "Related known words: " + ", ".join(anchor_words) + "."
                    source_sentence = f"{source_sentence or ''} {anchor_hint}".strip()

            seeds.append(
                ExerciseSeed(
                    english_lemma=item.english_lemma,
                    russian_translation=item.russian_translation,
                    source_sentence=source_sentence,
                )
            )
        if len(seeds) > 1:
            randomizer = secrets.SystemRandom()
            randomizer.shuffle(seeds)

        async def _run_generation() -> tuple[list[dict], str]:
            batch_size = 5
            if size > batch_size and len(seeds) >= batch_size:
                from app.modules.ai_services.contracts import GenerateExercisesRequest as GER
                batches = []
                remaining = size
                batch_idx = 0
                while remaining > 0:
                    batch_count = min(batch_size, remaining)
                    batch_seeds = []
                    for i in range(min(batch_size, len(seeds))):
                        seed_idx = (batch_idx * batch_size + i) % len(seeds)
                        batch_seeds.append(seeds[seed_idx])
                    batches.append(
                        GER(size=batch_count, cefr_level=cefr_level, mode=mode, seeds=batch_seeds)
                    )
                    remaining -= batch_count
                    batch_idx += 1

                try:
                    batch_responses = await ai_service.generate_exercises_batch(batches)
                except TranslationProviderUnavailableError as exc:
                    raise RuntimeError(str(exc)) from exc

                all_exercises = []
                for response in batch_responses:
                    all_exercises.extend(response.exercises)

                exercises_dicts = [
                    {
                        "prompt": item.prompt,
                        "answer": item.answer,
                        "exercise_type": item.exercise_type,
                        "options": item.options,
                    }
                    for item in all_exercises[:size]
                ]
                return (
                    exercises_dicts,
                    f"AI batch generation used (batches={len(batches)}; graph_anchors_used={anchors_used_count})",
                )
            else:
                try:
                    ai_response = await ai_service.generate_exercises_async(
                        GenerateExercisesRequest(size=size, cefr_level=cefr_level, mode=mode, seeds=seeds)
                    )
                except TranslationProviderUnavailableError as exc:
                    raise RuntimeError(str(exc)) from exc

                exercises_dicts = [
                    {
                        "prompt": item.prompt,
                        "answer": item.answer,
                        "exercise_type": item.exercise_type,
                        "options": item.options,
                    }
                    for item in ai_response.exercises
                ]
                return (
                    exercises_dicts,
                    f"AI generation used ({ai_response.provider_note}; graph_anchors_used={anchors_used_count})",
                )

        exercises_dicts, note = asyncio.run(_run_generation())
        return {"exercises": exercises_dicts, "note": note}

    except Exception as exc:
        logger.exception(
            "generate_exercises_for_user failed for user=%s mode=%s size=%s",
            user_id,
            mode,
            size,
        )
        raise self.retry(exc=exc)
    finally:
        db.close()
