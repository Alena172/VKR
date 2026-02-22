from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LearningSessionModel(Base):
    __tablename__ = "learning_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    correct: Mapped[int] = mapped_column(Integer, nullable=False)
    accuracy: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)


class LearningSessionAnswerModel(Base):
    __tablename__ = "learning_session_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("learning_sessions.id"), nullable=False, index=True)
    exercise_id: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_answer: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    user_answer: Mapped[str] = mapped_column(String(1000), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    explanation_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
