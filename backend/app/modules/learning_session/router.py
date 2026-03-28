from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.learning_session.repository import learning_session_repository
from app.modules.learning_session.schemas import (
    SessionAnswerRead,
    SessionHistoryResponse,
    SessionSubmitRequest,
    SessionSubmitResponse,
    SessionSummary,
)
from app.modules.learning_session.submission_service import learning_session_submission_service
from app.modules.users.repository import users_repository

router = APIRouter(prefix="/sessions", tags=["learning_session"])


@router.get("", response_model=list[SessionSummary])
def list_sessions(
    user_id: int | None = Query(default=None, ge=1),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[SessionSummary]:
    if user_id is not None and user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return learning_session_repository.list_sessions(db, user_id=user_id or current_user_id)


@router.get("/me", response_model=SessionHistoryResponse)
def list_my_sessions(
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    min_accuracy: float | None = Query(default=None, ge=0.0, le=1.0),
    max_accuracy: float | None = Query(default=None, ge=0.0, le=1.0),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SessionHistoryResponse:
    if min_accuracy is not None and max_accuracy is not None and min_accuracy > max_accuracy:
        raise HTTPException(status_code=400, detail="min_accuracy cannot be greater than max_accuracy")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from cannot be after date_to")

    created_from = datetime.combine(date_from, time.min) if date_from is not None else None
    created_to = datetime.combine(date_to + timedelta(days=1), time.min) if date_to is not None else None

    items = learning_session_repository.list_sessions_paginated(
        db,
        user_id=current_user_id,
        limit=limit,
        offset=offset,
        min_accuracy=min_accuracy,
        max_accuracy=max_accuracy,
        created_from=created_from,
        created_to=created_to,
    )
    total = learning_session_repository.count_sessions(
        db,
        user_id=current_user_id,
        min_accuracy=min_accuracy,
        max_accuracy=max_accuracy,
        created_from=created_from,
        created_to=created_to,
    )
    return SessionHistoryResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/{session_id}/answers", response_model=list[SessionAnswerRead])
def list_session_answers(
    session_id: int,
    user_id: int | None = Query(default=None, ge=1),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[SessionAnswerRead]:
    if user_id is not None and user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    target_user_id = user_id or current_user_id
    answers = learning_session_repository.list_answers_by_session(
        db,
        session_id=session_id,
        user_id=target_user_id,
    )
    if answers is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return answers


@router.get("/me/{session_id}/answers", response_model=list[SessionAnswerRead])
def list_my_session_answers(
    session_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[SessionAnswerRead]:
    answers = learning_session_repository.list_answers_by_session(
        db,
        session_id=session_id,
        user_id=current_user_id,
    )
    if answers is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return answers


@router.post("/submit", response_model=SessionSubmitResponse)
async def submit_session(
    payload: SessionSubmitRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SessionSubmitResponse:
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, target_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return await learning_session_submission_service.submit(
        db=db,
        user_id=target_user_id,
        user_cefr_level=user.cefr_level,
        answers=payload.answers,
    )
