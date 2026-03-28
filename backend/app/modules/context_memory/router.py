from datetime import datetime, timedelta
import re
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.context_memory.models import WordProgressModel
from app.modules.context_memory.repository import context_repository
from app.modules.context_memory.recommendation_scoring_service import recommendation_scoring_service
from app.modules.context_memory.schemas import (
    ContextGarbageCleanupResponse,
    ContextRecommendations,
    ProgressSnapshot,
    ReviewSummary,
    ReviewPlanResponse,
    ReviewQueueBulkSubmitRequest,
    ReviewQueueBulkSubmitResponse,
    ReviewQueueItem,
    ReviewSessionItem,
    ReviewSessionStartRequest,
    ReviewSessionStartResponse,
    ReviewQueueSubmitRequest,
    ReviewQueueResponse,
    UserContext,
    UserContextUpsert,
    WordProgressDeleteResponse,
    WordProgressListResponse,
    WordProgressRead,
)
from app.modules.learning_session.models import LearningSessionModel
from app.modules.users.repository import users_repository
from app.modules.vocabulary.models import VocabularyItemModel
from app.modules.vocabulary.repository import vocabulary_repository

router = APIRouter(prefix="/context", tags=["context_memory"])

_WORD_RE = re.compile(r"^[a-z][a-z'-]{0,48}$")


def _is_valid_review_word(value: str | None) -> bool:
    if not value:
        return False
    return bool(_WORD_RE.fullmatch(value.strip().lower()))


def _dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result

@router.get("/me", response_model=UserContext)
def get_context_me(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserContext:
    return get_context(user_id=current_user_id, current_user_id=current_user_id, db=db)


@router.put("/me", response_model=UserContext)
def upsert_context_me(
    payload: UserContextUpsert,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserContext:
    return upsert_context(user_id=current_user_id, payload=payload, current_user_id=current_user_id, db=db)


@router.get("/me/recommendations", response_model=ContextRecommendations)
def get_recommendations_me(
    limit: int = Query(default=10, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ContextRecommendations:
    return get_recommendations(
        user_id=current_user_id,
        limit=limit,
        current_user_id=current_user_id,
        db=db,
    )


@router.get("/me/review-queue", response_model=ReviewQueueResponse)
def get_review_queue_me(
    limit: int = Query(default=20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    return get_review_queue(
        user_id=current_user_id,
        limit=limit,
        current_user_id=current_user_id,
        db=db,
    )


@router.post("/me/review-queue/submit", response_model=WordProgressRead)
def submit_review_queue_item_me(
    payload: ReviewQueueSubmitRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressRead:
    return submit_review_queue_item(
        user_id=current_user_id,
        payload=payload,
        current_user_id=current_user_id,
        db=db,
    )


@router.post("/me/review-queue/submit-bulk", response_model=ReviewQueueBulkSubmitResponse)
def submit_review_queue_bulk_me(
    payload: ReviewQueueBulkSubmitRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewQueueBulkSubmitResponse:
    return submit_review_queue_bulk(
        user_id=current_user_id,
        payload=payload,
        current_user_id=current_user_id,
        db=db,
    )


@router.post("/me/review-session/start", response_model=ReviewSessionStartResponse)
def start_review_session_me(
    payload: ReviewSessionStartRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewSessionStartResponse:
    return start_review_session(
        user_id=current_user_id,
        payload=payload,
        current_user_id=current_user_id,
        db=db,
    )


@router.get("/me/word-progress", response_model=WordProgressListResponse)
def list_word_progress_me(
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Literal["all", "due", "upcoming", "mastered", "troubled"] = Query(default="all"),
    q: str | None = Query(default=None, max_length=200),
    sort_by: Literal["next_review_at", "error_count", "correct_streak"] = Query(default="next_review_at"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    min_streak: int = Query(default=3, ge=1, le=50),
    min_errors: int = Query(default=3, ge=1, le=50),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressListResponse:
    return list_word_progress(
        user_id=current_user_id,
        limit=limit,
        offset=offset,
        status=status,
        q=q,
        sort_by=sort_by,
        sort_order=sort_order,
        min_streak=min_streak,
        min_errors=min_errors,
        current_user_id=current_user_id,
        db=db,
    )


@router.get("/me/word-progress/{word}", response_model=WordProgressRead)
def get_word_progress_me(
    word: str,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressRead:
    return get_word_progress(user_id=current_user_id, word=word, current_user_id=current_user_id, db=db)


@router.delete("/me/word-progress/{word}", response_model=WordProgressDeleteResponse)
def delete_word_progress_me(
    word: str,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressDeleteResponse:
    return delete_word_progress(user_id=current_user_id, word=word, current_user_id=current_user_id, db=db)


@router.get("/me/review-plan", response_model=ReviewPlanResponse)
def get_review_plan_me(
    limit: int = Query(default=10, ge=1, le=100),
    horizon_hours: int = Query(default=24, ge=1, le=168),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewPlanResponse:
    return get_review_plan(
        user_id=current_user_id,
        limit=limit,
        horizon_hours=horizon_hours,
        current_user_id=current_user_id,
        db=db,
    )


@router.post("/me/cleanup-garbage", response_model=ContextGarbageCleanupResponse)
def cleanup_context_garbage_me(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ContextGarbageCleanupResponse:
    return cleanup_context_garbage(user_id=current_user_id, current_user_id=current_user_id, db=db)


@router.get("/me/progress", response_model=ProgressSnapshot)
def progress_me(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProgressSnapshot:
    return progress(user_id=None, current_user_id=current_user_id, db=db)


@router.get("/me/review-summary", response_model=ReviewSummary)
def review_summary_me(
    min_streak: int = Query(default=3, ge=1, le=50),
    min_errors: int = Query(default=3, ge=1, le=50),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewSummary:
    return review_summary(
        user_id=current_user_id,
        min_streak=min_streak,
        min_errors=min_errors,
        current_user_id=current_user_id,
        db=db,
    )


@router.get("/progress", response_model=ProgressSnapshot)
def progress(
    user_id: int | None = Query(default=None, ge=1),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProgressSnapshot:
    total_stmt = select(func.count(LearningSessionModel.id))
    avg_stmt = select(func.avg(LearningSessionModel.accuracy))

    if user_id is not None and user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    target_user_id = user_id or current_user_id
    total_stmt = total_stmt.where(LearningSessionModel.user_id == target_user_id)
    avg_stmt = avg_stmt.where(LearningSessionModel.user_id == target_user_id)

    total = db.scalar(total_stmt) or 0
    avg = db.scalar(avg_stmt) or 0.0

    return ProgressSnapshot(
        user_id=target_user_id,
        total_sessions=int(total),
        avg_accuracy=round(float(avg), 4),
    )


@router.get("/review-summary", response_model=ReviewSummary)
def review_summary(
    user_id: int = Query(ge=1),
    min_streak: int = Query(default=3, ge=1, le=50),
    min_errors: int = Query(default=3, ge=1, le=50),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewSummary:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    vocab_exists = exists(
        select(1).where(
            VocabularyItemModel.user_id == user_id,
            VocabularyItemModel.english_lemma == WordProgressModel.word,
        )
    )
    base_stmt = select(WordProgressModel).where(
        WordProgressModel.user_id == user_id,
        vocab_exists,
    )

    total_tracked = int(db.scalar(select(func.count()).select_from(base_stmt.subquery())) or 0)
    now_utc = datetime.utcnow()
    due_now = int(
        db.scalar(
            select(func.count()).select_from(
                base_stmt.where(WordProgressModel.next_review_at <= now_utc).subquery()
            )
        )
        or 0
    )
    mastered = int(
        db.scalar(
            select(func.count()).select_from(
                base_stmt.where(WordProgressModel.correct_streak >= min_streak).subquery()
            )
        )
        or 0
    )
    troubled = int(
        db.scalar(
            select(func.count()).select_from(
                base_stmt.where(WordProgressModel.error_count >= min_errors).subquery()
            )
        )
        or 0
    )

    return ReviewSummary(
        user_id=user_id,
        total_tracked=total_tracked,
        due_now=due_now,
        mastered=mastered,
        troubled=troubled,
    )


@router.get("/{user_id}", response_model=UserContext)
def get_context(
    user_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserContext:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    context = context_repository.get_by_user_id(db, user_id)
    if context is None:
        raise HTTPException(status_code=404, detail="Context not found")
    return context


@router.put("/{user_id}", response_model=UserContext)
def upsert_context(
    user_id: int,
    payload: UserContextUpsert,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> UserContext:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return context_repository.upsert(db, user_id, payload)


@router.get("/{user_id}/recommendations", response_model=ContextRecommendations)
def get_recommendations(
    user_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ContextRecommendations:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    snapshot = recommendation_scoring_service.build_snapshot(
        db=db,
        user_id=user_id,
        limit=limit,
    )
    words = snapshot.ranked_words(limit)

    recent_error_words: list[str] = []
    for word in snapshot.recent_error_words_stream:
        if word not in recent_error_words:
            recent_error_words.append(word)
        if len(recent_error_words) >= limit:
            break

    return ContextRecommendations(
        user_id=user_id,
        words=words,
        recent_error_words=recent_error_words,
        difficult_words=snapshot.difficult_words[:limit],
        scores={word: round(snapshot.scores[word], 6) for word in words},
        next_review_at={
            word: snapshot.due_progress_map.get(word).next_review_at if snapshot.due_progress_map.get(word) else None
            for word in words
        },
    )


@router.get("/{user_id}/review-queue", response_model=ReviewQueueResponse)
def get_review_queue(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch extra rows and filter to valid vocabulary lemmas to avoid polluted queue.
    due_progress = context_repository.list_due_word_progress(db, user_id=user_id, limit=limit * 5)
    total_due_raw = context_repository.count_due_word_progress(db, user_id=user_id)

    words = [row.word for row in due_progress]
    translation_map = vocabulary_repository.get_translation_map(db, user_id=user_id, english_lemmas=words)

    items = [
        ReviewQueueItem(
            word=row.word,
            russian_translation=translation_map.get(row.word),
            next_review_at=row.next_review_at,
            error_count=row.error_count,
            correct_streak=row.correct_streak,
        )
        for row in due_progress
        if _is_valid_review_word(row.word)
    ]
    items = items[:limit]
    total_due = min(total_due_raw, len(items))

    return ReviewQueueResponse(user_id=user_id, total_due=total_due, items=items)


@router.post("/{user_id}/review-queue/submit", response_model=WordProgressRead)
def submit_review_queue_item(
    user_id: int,
    payload: ReviewQueueSubmitRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressRead:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    normalized_word = payload.word.strip().lower()
    if not _is_valid_review_word(normalized_word):
        raise HTTPException(status_code=400, detail="Word must be a single english token")

    progress = context_repository.update_word_progress(
        db,
        user_id=user_id,
        word=normalized_word,
        is_correct=payload.is_correct,
    )
    if progress is None:
        raise HTTPException(status_code=400, detail="Word is empty")

    if not payload.is_correct:
        context_repository.add_difficult_words(
            db,
            user_id=user_id,
            words=[normalized_word],
            default_cefr_level=user.cefr_level,
        )
    else:
        db.commit()

    db.refresh(progress)
    translation_map = vocabulary_repository.get_translation_map(
        db,
        user_id=user_id,
        english_lemmas=[progress.word],
    )
    return WordProgressRead(
        user_id=progress.user_id,
        word=progress.word,
        russian_translation=translation_map.get(progress.word),
        error_count=progress.error_count,
        correct_streak=progress.correct_streak,
        next_review_at=progress.next_review_at,
    )


@router.post("/{user_id}/review-queue/submit-bulk", response_model=ReviewQueueBulkSubmitResponse)
def submit_review_queue_bulk(
    user_id: int,
    payload: ReviewQueueBulkSubmitRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewQueueBulkSubmitResponse:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if not payload.items:
        return ReviewQueueBulkSubmitResponse(user_id=user_id, updated=[])

    incorrect_words: list[str] = []
    updated_progress: list[WordProgressRead] = []
    for item in payload.items:
        normalized_word = item.word.strip().lower()
        if not _is_valid_review_word(normalized_word):
            continue
        progress = context_repository.update_word_progress(
            db,
            user_id=user_id,
            word=normalized_word,
            is_correct=item.is_correct,
        )
        if progress is None:
            continue

        if not item.is_correct:
            incorrect_words.append(normalized_word)

        updated_progress.append(
            WordProgressRead(
                user_id=progress.user_id,
                word=progress.word,
                russian_translation=None,
                error_count=progress.error_count,
                correct_streak=progress.correct_streak,
                next_review_at=progress.next_review_at,
            )
        )

    if incorrect_words:
        context_repository.add_difficult_words(
            db,
            user_id=user_id,
            words=incorrect_words,
            default_cefr_level=user.cefr_level,
        )
    else:
        db.commit()

    translation_map = vocabulary_repository.get_translation_map(
        db,
        user_id=user_id,
        english_lemmas=[item.word for item in updated_progress],
    )
    for item in updated_progress:
        item.russian_translation = translation_map.get(item.word)

    return ReviewQueueBulkSubmitResponse(user_id=user_id, updated=updated_progress)


@router.post("/{user_id}/review-session/start", response_model=ReviewSessionStartResponse)
def start_review_session(
    user_id: int,
    payload: ReviewSessionStartRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewSessionStartResponse:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.mode == "srs":
        due_rows = context_repository.list_due_word_progress(db, user_id=user_id, limit=payload.size * 5)
        words = _dedupe_keep_order(
            [row.word for row in due_rows if _is_valid_review_word(row.word)]
        )[: payload.size]
        translation_map = vocabulary_repository.get_translation_map(db, user_id=user_id, english_lemmas=words)
        definition_map = vocabulary_repository.get_definition_map(db, user_id=user_id, english_lemmas=words)
        row_map = {row.word: row for row in due_rows}

        items = [
            ReviewSessionItem(
                word=word,
                russian_translation=translation_map.get(word),
                context_definition=definition_map.get(word),
                next_review_at=row_map[word].next_review_at if word in row_map else None,
                error_count=row_map[word].error_count if word in row_map else 0,
                correct_streak=row_map[word].correct_streak if word in row_map else 0,
            )
            for word in words
        ]
        return ReviewSessionStartResponse(
            user_id=user_id,
            mode="srs",
            total_items=len(items),
            items=items,
        )

    # Random mode: select unique words from vocabulary without replacement.
    # SystemRandom uses OS entropy source.
    vocabulary_items = vocabulary_repository.list_items(db, user_id=user_id)
    unique_words = _dedupe_keep_order(
        [item.english_lemma for item in vocabulary_items if _is_valid_review_word(item.english_lemma)]
    )
    if not unique_words:
        return ReviewSessionStartResponse(user_id=user_id, mode="random", total_items=0, items=[])

    sample_size = min(payload.size, len(unique_words))
    random_words = secrets.SystemRandom().sample(unique_words, k=sample_size)
    translation_map = vocabulary_repository.get_translation_map(db, user_id=user_id, english_lemmas=random_words)
    definition_map = vocabulary_repository.get_definition_map(db, user_id=user_id, english_lemmas=random_words)
    progress_map = context_repository.get_word_progress_map(db, user_id=user_id, words=random_words)

    items = [
        ReviewSessionItem(
            word=word,
            russian_translation=translation_map.get(word),
            context_definition=definition_map.get(word),
            next_review_at=progress_map[word].next_review_at if word in progress_map else None,
            error_count=progress_map[word].error_count if word in progress_map else 0,
            correct_streak=progress_map[word].correct_streak if word in progress_map else 0,
        )
        for word in random_words
    ]
    return ReviewSessionStartResponse(
        user_id=user_id,
        mode="random",
        total_items=len(items),
        items=items,
    )


@router.get("/{user_id}/word-progress", response_model=WordProgressListResponse)
def list_word_progress(
    user_id: int,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Literal["all", "due", "upcoming", "mastered", "troubled"] = Query(default="all"),
    q: str | None = Query(default=None, max_length=200),
    sort_by: Literal["next_review_at", "error_count", "correct_streak"] = Query(default="next_review_at"),
    sort_order: Literal["asc", "desc"] = Query(default="asc"),
    min_streak: int = Query(default=3, ge=1, le=50),
    min_errors: int = Query(default=3, ge=1, le=50),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressListResponse:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    rows = context_repository.list_word_progress(
        db,
        user_id=user_id,
        limit=limit,
        offset=offset,
        status=status,
        q=q,
        sort_by=sort_by,
        sort_order=sort_order,
        min_streak=min_streak,
        min_errors=min_errors,
    )
    total = context_repository.count_word_progress(
        db,
        user_id=user_id,
        status=status,
        q=q,
        min_streak=min_streak,
        min_errors=min_errors,
    )
    words = [row.word for row in rows]
    translation_map = vocabulary_repository.get_translation_map(db, user_id=user_id, english_lemmas=words)

    items = [
        WordProgressRead(
            user_id=row.user_id,
            word=row.word,
            russian_translation=translation_map.get(row.word),
            error_count=row.error_count,
            correct_streak=row.correct_streak,
            next_review_at=row.next_review_at,
        )
        for row in rows
    ]
    return WordProgressListResponse(user_id=user_id, total=total, limit=limit, offset=offset, items=items)


@router.get("/{user_id}/word-progress/{word}", response_model=WordProgressRead)
def get_word_progress(
    user_id: int,
    word: str,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressRead:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    progress = context_repository.get_word_progress(db, user_id=user_id, word=word)
    if progress is None:
        raise HTTPException(status_code=404, detail="Word progress not found")

    translation_map = vocabulary_repository.get_translation_map(
        db,
        user_id=user_id,
        english_lemmas=[progress.word],
    )
    return WordProgressRead(
        user_id=progress.user_id,
        word=progress.word,
        russian_translation=translation_map.get(progress.word),
        error_count=progress.error_count,
        correct_streak=progress.correct_streak,
        next_review_at=progress.next_review_at,
    )


@router.delete("/{user_id}/word-progress/{word}", response_model=WordProgressDeleteResponse)
def delete_word_progress(
    user_id: int,
    word: str,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> WordProgressDeleteResponse:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    progress_deleted = context_repository.delete_word_progress(db, user_id=user_id, word=word)
    removed_from_difficult_words = context_repository.remove_difficult_word(db, user_id=user_id, word=word)
    db.commit()

    return WordProgressDeleteResponse(
        user_id=user_id,
        word=word.strip().lower(),
        progress_deleted=progress_deleted,
        removed_from_difficult_words=removed_from_difficult_words,
    )


@router.get("/{user_id}/review-plan", response_model=ReviewPlanResponse)
def get_review_plan(
    user_id: int,
    limit: int = Query(default=10, ge=1, le=100),
    horizon_hours: int = Query(default=24, ge=1, le=168),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ReviewPlanResponse:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    due_progress = context_repository.list_due_word_progress(db, user_id=user_id, limit=limit)
    upcoming_progress = context_repository.list_upcoming_word_progress(
        db,
        user_id=user_id,
        horizon=timedelta(hours=horizon_hours),
        limit=limit,
    )

    all_words = [row.word for row in due_progress] + [row.word for row in upcoming_progress]
    translation_map = vocabulary_repository.get_translation_map(db, user_id=user_id, english_lemmas=all_words)

    due_now = [
        ReviewQueueItem(
            word=row.word,
            russian_translation=translation_map.get(row.word),
            next_review_at=row.next_review_at,
            error_count=row.error_count,
            correct_streak=row.correct_streak,
        )
        for row in due_progress
        if _is_valid_review_word(row.word)
    ]
    upcoming = [
        ReviewQueueItem(
            word=row.word,
            russian_translation=translation_map.get(row.word),
            next_review_at=row.next_review_at,
            error_count=row.error_count,
            correct_streak=row.correct_streak,
        )
        for row in upcoming_progress
        if _is_valid_review_word(row.word)
    ]

    snapshot = recommendation_scoring_service.build_snapshot(
        db=db,
        user_id=user_id,
        limit=limit,
    )

    return ReviewPlanResponse(
        user_id=user_id,
        due_count=len(due_now),
        upcoming_count=len(upcoming),
        due_now=due_now,
        upcoming=upcoming,
        recommended_words=snapshot.ranked_words(limit),
    )


@router.post("/{user_id}/cleanup-garbage", response_model=ContextGarbageCleanupResponse)
def cleanup_context_garbage(
    user_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ContextGarbageCleanupResponse:
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    vocabulary_words = {
        item.english_lemma.strip().lower()
        for item in vocabulary_repository.list_items(db, user_id=user_id)
        if _is_valid_review_word(item.english_lemma)
    }
    removed_word_progress, removed_difficult_words = context_repository.cleanup_user_garbage(
        db,
        user_id=user_id,
        vocabulary_words=vocabulary_words,
    )
    db.commit()
    return ContextGarbageCleanupResponse(
        user_id=user_id,
        removed_word_progress=removed_word_progress,
        removed_difficult_words=removed_difficult_words,
    )
