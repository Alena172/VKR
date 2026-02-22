from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.analytics.schemas import ProgressSnapshot, ReviewSummary
from app.modules.context_memory.repository import context_repository
from app.modules.context_memory.models import WordProgressModel
from app.modules.learning_session.models import LearningSessionModel
from app.modules.users.repository import users_repository
from app.modules.vocabulary.models import VocabularyItemModel

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/progress/me", response_model=ProgressSnapshot)
def progress_me(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> ProgressSnapshot:
    return progress(user_id=None, current_user_id=current_user_id, db=db)


@router.get("/review-summary/me", response_model=ReviewSummary)
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
