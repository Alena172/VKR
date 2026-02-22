from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class UserContextModel(Base):
    __tablename__ = "user_contexts"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    cefr_level: Mapped[str] = mapped_column(String(2), nullable=False)
    goals: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    difficult_words: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class WordProgressModel(Base):
    __tablename__ = "word_progress"
    __table_args__ = (UniqueConstraint("user_id", "word", name="uq_word_progress_user_word"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    word: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    next_review_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, index=True)
