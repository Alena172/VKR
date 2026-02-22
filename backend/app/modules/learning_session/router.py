from datetime import date, datetime, time, timedelta
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.ai_services.contracts import ExplainErrorRequest
from app.modules.ai_services.service import ai_service
from app.modules.context_memory.repository import context_repository
from app.modules.learning_session.repository import AnswerPersistPayload, learning_session_repository
from app.modules.learning_session.evaluation import is_answer_correct
from app.modules.learning_session.schemas import (
    SessionAnswerRead,
    SessionAnswerFeedback,
    SessionHistoryResponse,
    SessionSubmitRequest,
    SessionSubmitResponse,
    SessionSummary,
)
from app.modules.users.repository import users_repository

router = APIRouter(prefix="/sessions", tags=["learning_session"])


_WORD_RE = re.compile(r"^[a-z][a-z'-]{0,48}$")


def _normalize_word_candidate(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().lower().strip(" \t\n\r\"'`.,!?;:()[]{}")
    if not candidate or not _WORD_RE.fullmatch(candidate):
        return None
    return candidate


def _extract_progress_word(
    *,
    prompt: str | None,
    expected_answer: str | None,
    vocabulary_words: set[str],
) -> str | None:
    # For word scramble tasks answer is usually the target english lemma.
    normalized_answer = _normalize_word_candidate(expected_answer)
    if normalized_answer and (not vocabulary_words or normalized_answer in vocabulary_words):
        return normalized_answer

    if not prompt:
        return None

    # For definition match tasks prompt often ends with ": <word>".
    after_colon = prompt.split(":", maxsplit=1)[-1]
    normalized_prompt_word = _normalize_word_candidate(after_colon)
    if normalized_prompt_word and (not vocabulary_words or normalized_prompt_word in vocabulary_words):
        return normalized_prompt_word

    return None


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
def submit_session(
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

    feedback: list[SessionAnswerFeedback] = []
    to_persist: list[AnswerPersistPayload] = []
    difficult_words_to_add: list[str] = []
    total = len(payload.answers)
    correct = 0

    for answer in payload.answers:
        evaluated_is_correct = is_answer_correct(answer.expected_answer, answer.user_answer)
        if evaluated_is_correct:
            correct += 1
        explanation_ru: str | None = None

        if (
            not evaluated_is_correct
            and answer.prompt
            and answer.expected_answer
        ):
            ai_explanation = ai_service.explain_error(
                ExplainErrorRequest(
                    english_prompt=answer.prompt,
                    user_answer=answer.user_answer,
                    expected_answer=answer.expected_answer,
                )
            )
            explanation_ru = ai_explanation.explanation_ru
            feedback.append(
                SessionAnswerFeedback(
                    exercise_id=answer.exercise_id,
                    explanation_ru=explanation_ru,
                )
            )
            prompt_word = _extract_progress_word(
                prompt=answer.prompt,
                expected_answer=answer.expected_answer,
                vocabulary_words=set(),
            )
            if prompt_word:
                difficult_words_to_add.append(prompt_word)

        progress_word = _extract_progress_word(
            prompt=answer.prompt,
            expected_answer=answer.expected_answer,
            vocabulary_words=set(),
        )
        if progress_word:
            context_repository.update_word_progress(
                db,
                user_id=target_user_id,
                word=progress_word,
                is_correct=evaluated_is_correct,
            )

        to_persist.append(
            AnswerPersistPayload(
                exercise_id=answer.exercise_id,
                prompt=answer.prompt,
                expected_answer=answer.expected_answer,
                user_answer=answer.user_answer,
                is_correct=evaluated_is_correct,
                explanation_ru=explanation_ru,
            )
        )

    context_repository.add_difficult_words(
        db,
        user_id=target_user_id,
        words=difficult_words_to_add,
        default_cefr_level=user.cefr_level,
    )

    session_row = learning_session_repository.create_with_answers(
        db,
        user_id=target_user_id,
        total=total,
        correct=correct,
        accuracy=round((correct / total), 4) if total else 0.0,
        answers=to_persist,
    )

    return SessionSubmitResponse(session=session_row, incorrect_feedback=feedback)
