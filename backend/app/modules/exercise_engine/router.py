from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
import secrets

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.ai_services.contracts import ExerciseSeed, GenerateExercisesRequest
from app.modules.ai_services.service import TranslationProviderUnavailableError, ai_service
from app.modules.context_memory.repository import context_repository
from app.modules.exercise_engine.schemas import (
    ExerciseGenerateRequest,
    ExerciseGenerateRequestMe,
    ExerciseGenerateResponse,
    ExerciseItem,
)
from app.modules.users.repository import users_repository
from app.modules.vocabulary.repository import vocabulary_repository
from app.modules.exercise_engine.prefetch_service import prefetch_service

router = APIRouter(prefix="/exercises", tags=["exercise_engine"])


def _dedupe_vocabulary_by_lemma(vocabulary_items):
    # Keep the latest entry per lemma (incoming list is ordered by id desc).
    deduped = {}
    for item in vocabulary_items:
        key = item.english_lemma.strip().lower()
        if not key or key in deduped:
            continue
        deduped[key] = item
    return list(deduped.values())


async def _prefetch_for_user_background(
    user_id: int,
    vocabulary_ids: list[int],
    size: int,
    mode: str,
) -> None:
    """Background task to prefetch exercises for next request."""
    try:
        from app.core.db import SessionLocal
        
        db = SessionLocal()
        try:
            result = await _generate_for_user(
                user_id=user_id,
                vocabulary_ids=vocabulary_ids,
                size=size,
                mode=mode,
                db=db,
            )
            prefetch_service.store_prefetch(user_id, mode, result.exercises)
        finally:
            db.close()
    except Exception:
        # Silently fail prefetch - it's not critical
        pass


async def _generate_for_user(
    *,
    user_id: int,
    vocabulary_ids: list[int],
    size: int,
    mode: str,
    db: Session,
) -> ExerciseGenerateResponse:
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    vocabulary_items = vocabulary_repository.list_items(db, user_id=user_id)
    if vocabulary_ids:
        allowed = set(vocabulary_ids)
        vocabulary_items = [item for item in vocabulary_items if item.id in allowed]
    vocabulary_items = _dedupe_vocabulary_by_lemma(vocabulary_items)
    if not vocabulary_items:
        raise HTTPException(
            status_code=400,
            detail="Vocabulary is empty. Add words before generating exercises.",
        )
    if mode == "word_definition_match":
        unique_lemmas = {item.english_lemma.strip().lower() for item in vocabulary_items if item.english_lemma}
        if len(unique_lemmas) < 4:
            raise HTTPException(
                status_code=400,
                detail="Need at least 4 different words in vocabulary for definition matching.",
            )

    context = context_repository.get_by_user_id(db, user_id)
    cefr_level = context.cefr_level if context is not None else user.cefr_level

    seeds = [
        ExerciseSeed(
            english_lemma=item.english_lemma,
            russian_translation=item.russian_translation,
            source_sentence=item.source_sentence,
        )
        for item in vocabulary_items
    ]
    if len(seeds) > 1:
        randomizer = secrets.SystemRandom()
        randomizer.shuffle(seeds)

    # Batch generation for larger sets
    if size > 5 and len(seeds) >= 5:
        # Split into batches of 5
        batch_size = 5
        batches = []
        remaining = size
        
        # Create batches with rotating seed selection to ensure variety
        batch_idx = 0
        while remaining > 0:
            batch_count = min(batch_size, remaining)
            
            # Select seeds for this batch by rotating through the full seed list
            # This ensures each batch gets different words
            batch_seeds = []
            for i in range(min(batch_size, len(seeds))):
                seed_idx = (batch_idx * batch_size + i) % len(seeds)
                batch_seeds.append(seeds[seed_idx])
            
            batches.append(
                GenerateExercisesRequest(
                    size=batch_count,
                    cefr_level=cefr_level,
                    mode=mode,
                    seeds=batch_seeds,
                )
            )
            remaining -= batch_count
            batch_idx += 1
        
        # Generate in parallel
        try:
            batch_responses = await ai_service.generate_exercises_batch(batches)
        except TranslationProviderUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        all_exercises = []
        for response in batch_responses:
            all_exercises.extend(response.exercises)
        
        exercises = [
            ExerciseItem(
                prompt=item.prompt,
                answer=item.answer,
                exercise_type=item.exercise_type,
                options=item.options,
            )
            for item in all_exercises[:size]
        ]
        
        return ExerciseGenerateResponse(
            exercises=exercises,
            note=f"AI batch generation used (batches={len(batches)})",
        )
    else:
        # Single request for small sets
        try:
            ai_response = await ai_service.generate_exercises_async(
                GenerateExercisesRequest(size=size, cefr_level=cefr_level, mode=mode, seeds=seeds)
            )
        except TranslationProviderUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        exercises = [
            ExerciseItem(
                prompt=item.prompt,
                answer=item.answer,
                exercise_type=item.exercise_type,
                options=item.options,
            )
            for item in ai_response.exercises
        ]

        return ExerciseGenerateResponse(
            exercises=exercises,
            note=f"AI generation used ({ai_response.provider_note})",
        )


@router.post("/me/generate", response_model=ExerciseGenerateResponse)
async def generate_me(
    payload: ExerciseGenerateRequestMe,
    background_tasks: BackgroundTasks,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ExerciseGenerateResponse:
    # Try to use prefetched exercises first.
    prefetched: list[ExerciseItem] = []
    if prefetch_service.has_prefetch(current_user_id, payload.mode):
        prefetched = prefetch_service.get_prefetched(current_user_id, payload.mode, payload.size)
        if len(prefetched) >= payload.size:
            background_tasks.add_task(
                _prefetch_for_user_background,
                current_user_id,
                payload.vocabulary_ids,
                payload.size,
                payload.mode,
            )
            return ExerciseGenerateResponse(
                exercises=prefetched[:payload.size],
                note="Prefetched exercises (instant)",
            )

    # If prefetch is partial, generate only the missing amount and merge.
    missing = max(0, payload.size - len(prefetched))
    generated: list[ExerciseItem] = []
    generation_note = ""
    if missing > 0:
        generated_response = await _generate_for_user(
            user_id=current_user_id,
            vocabulary_ids=payload.vocabulary_ids,
            size=missing,
            mode=payload.mode,
            db=db,
        )
        generated = generated_response.exercises
        generation_note = generated_response.note

    merged = (prefetched + generated)[: payload.size]
    
    # Trigger background prefetch for next time
    background_tasks.add_task(
        _prefetch_for_user_background,
        current_user_id,
        payload.vocabulary_ids,
        payload.size,
        payload.mode,
    )

    if prefetched and generated:
        note = f"Prefetch + generation used ({len(prefetched)} + {len(generated)})"
    elif prefetched:
        note = "Prefetched exercises (instant)"
    else:
        note = generation_note or "AI generation used"

    return ExerciseGenerateResponse(exercises=merged, note=note)


@router.post("/generate", response_model=ExerciseGenerateResponse)
async def generate(
    payload: ExerciseGenerateRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ExerciseGenerateResponse:
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await _generate_for_user(
        user_id=target_user_id,
        vocabulary_ids=payload.vocabulary_ids,
        size=payload.size,
        mode=payload.mode,
        db=db,
    )
