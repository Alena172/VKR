from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.modules.learning_session.models import LearningSessionAnswerModel, LearningSessionModel


@dataclass
class AnswerPersistPayload:
    exercise_id: int
    prompt: str | None
    expected_answer: str | None
    user_answer: str
    is_correct: bool
    explanation_ru: str | None


class LearningSessionRepository:
    def _apply_session_filters(
        self,
        stmt: Select,
        *,
        user_id: int | None,
        min_accuracy: float | None = None,
        max_accuracy: float | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> Select:
        if user_id is not None:
            stmt = stmt.where(LearningSessionModel.user_id == user_id)
        if min_accuracy is not None:
            stmt = stmt.where(LearningSessionModel.accuracy >= min_accuracy)
        if max_accuracy is not None:
            stmt = stmt.where(LearningSessionModel.accuracy <= max_accuracy)
        if created_from is not None:
            stmt = stmt.where(LearningSessionModel.created_at >= created_from)
        if created_to is not None:
            stmt = stmt.where(LearningSessionModel.created_at < created_to)
        return stmt

    def list_sessions(self, db: Session, user_id: int | None) -> list[LearningSessionModel]:
        stmt = select(LearningSessionModel)
        stmt = self._apply_session_filters(stmt, user_id=user_id)
        stmt = stmt.order_by(LearningSessionModel.id.desc())
        return list(db.scalars(stmt))

    def list_sessions_paginated(
        self,
        db: Session,
        *,
        user_id: int,
        limit: int,
        offset: int,
        min_accuracy: float | None = None,
        max_accuracy: float | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[LearningSessionModel]:
        stmt = select(LearningSessionModel)
        stmt = self._apply_session_filters(
            stmt,
            user_id=user_id,
            min_accuracy=min_accuracy,
            max_accuracy=max_accuracy,
            created_from=created_from,
            created_to=created_to,
        )
        stmt = stmt.order_by(LearningSessionModel.id.desc()).limit(limit).offset(offset)
        return list(db.scalars(stmt))

    def count_sessions(
        self,
        db: Session,
        *,
        user_id: int,
        min_accuracy: float | None = None,
        max_accuracy: float | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        stmt = select(func.count(LearningSessionModel.id))
        stmt = self._apply_session_filters(
            stmt,
            user_id=user_id,
            min_accuracy=min_accuracy,
            max_accuracy=max_accuracy,
            created_from=created_from,
            created_to=created_to,
        )
        return int(db.scalar(stmt) or 0)

    def list_answers_by_session(
        self,
        db: Session,
        session_id: int,
        user_id: int,
    ) -> list[LearningSessionAnswerModel] | None:
        session_stmt = select(LearningSessionModel).where(
            LearningSessionModel.id == session_id,
            LearningSessionModel.user_id == user_id,
        )
        session_row = db.scalar(session_stmt)
        if session_row is None:
            return None

        answers_stmt = (
            select(LearningSessionAnswerModel)
            .where(LearningSessionAnswerModel.session_id == session_id)
            .order_by(LearningSessionAnswerModel.id.asc())
        )
        return list(db.scalars(answers_stmt))

    def create_with_answers(
        self,
        db: Session,
        user_id: int,
        total: int,
        correct: int,
        accuracy: float,
        answers: list[AnswerPersistPayload],
    ) -> LearningSessionModel:
        session_row = LearningSessionModel(
            user_id=user_id,
            total=total,
            correct=correct,
            accuracy=accuracy,
        )
        db.add(session_row)
        db.flush()

        for answer in answers:
            db.add(
                LearningSessionAnswerModel(
                    session_id=session_row.id,
                    exercise_id=answer.exercise_id,
                    prompt=answer.prompt,
                    expected_answer=answer.expected_answer,
                    user_answer=answer.user_answer,
                    is_correct=answer.is_correct,
                    explanation_ru=answer.explanation_ru,
                )
            )

        db.commit()
        db.refresh(session_row)
        return session_row

    def list_recent_incorrect_words(
        self,
        db: Session,
        user_id: int,
        limit: int = 20,
        unique: bool = True,
    ) -> list[str]:
        stmt = (
            select(LearningSessionAnswerModel.prompt)
            .join(
                LearningSessionModel,
                LearningSessionModel.id == LearningSessionAnswerModel.session_id,
            )
            .where(
                LearningSessionModel.user_id == user_id,
                LearningSessionAnswerModel.is_correct.is_(False),
                LearningSessionAnswerModel.prompt.is_not(None),
            )
            .order_by(LearningSessionAnswerModel.id.desc())
            .limit(limit)
        )
        prompts = list(db.scalars(stmt))

        words: list[str] = []
        for prompt in prompts:
            prompt_text = (prompt or "").strip()
            if not prompt_text:
                continue
            word = prompt_text.split(":", maxsplit=1)[-1].strip().lower()
            if not word:
                continue
            if unique:
                if word not in words:
                    words.append(word)
            else:
                words.append(word)
        return words


learning_session_repository = LearningSessionRepository()
