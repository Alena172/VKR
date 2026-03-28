from datetime import datetime, timedelta
import json
from typing import Literal
import re

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.modules.context_memory.models import UserContextModel, WordProgressModel
from app.modules.context_memory.schemas import UserContext, UserContextUpsert


class ContextMemoryRepository:
    _SRS_STEPS_DAYS = [1, 3, 7, 14, 30, 60]
    _WORD_RE = re.compile(r"^[a-z][a-z'-]{0,48}$")

    @classmethod
    def _normalize_valid_word(cls, value: str | None) -> str | None:
        if not value:
            return None
        normalized = value.strip().lower()
        if not normalized or not cls._WORD_RE.fullmatch(normalized):
            return None
        return normalized

    def get_by_user_id(self, db: Session, user_id: int) -> UserContext | None:
        row = db.get(UserContextModel, user_id)
        if row is None:
            return None
        return UserContext(
            user_id=row.user_id,
            cefr_level=row.cefr_level,
            goals=json.loads(row.goals),
            difficult_words=json.loads(row.difficult_words),
        )

    def upsert(self, db: Session, user_id: int, payload: UserContextUpsert) -> UserContext:
        row = db.get(UserContextModel, user_id)
        serialized_goals = json.dumps(payload.goals, ensure_ascii=False)
        serialized_difficult = json.dumps(payload.difficult_words, ensure_ascii=False)

        if row is None:
            row = UserContextModel(
                user_id=user_id,
                cefr_level=payload.cefr_level,
                goals=serialized_goals,
                difficult_words=serialized_difficult,
            )
            db.add(row)
        else:
            row.cefr_level = payload.cefr_level
            row.goals = serialized_goals
            row.difficult_words = serialized_difficult

        db.commit()
        db.refresh(row)

        return UserContext(
            user_id=row.user_id,
            cefr_level=row.cefr_level,
            goals=json.loads(row.goals),
            difficult_words=json.loads(row.difficult_words),
        )

    def add_difficult_words(
        self,
        db: Session,
        user_id: int,
        words: list[str],
        default_cefr_level: str,
        *,
        auto_commit: bool = True,
    ) -> UserContext:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_word in words:
            word = self._normalize_valid_word(raw_word)
            if not word or word in seen:
                continue
            seen.add(word)
            normalized.append(word)
        if not normalized:
            context = self.get_by_user_id(db, user_id)
            if context is not None:
                return context
            row = UserContextModel(
                user_id=user_id,
                cefr_level=default_cefr_level,
                goals="[]",
                difficult_words="[]",
            )
            db.add(row)
            if auto_commit:
                db.commit()
                db.refresh(row)
            else:
                db.flush()
            return UserContext(
                user_id=row.user_id,
                cefr_level=row.cefr_level,
                goals=json.loads(row.goals),
                difficult_words=json.loads(row.difficult_words),
            )

        row = db.get(UserContextModel, user_id)
        if row is None:
            merged_words = sorted(set(normalized))
            row = UserContextModel(
                user_id=user_id,
                cefr_level=default_cefr_level,
                goals="[]",
                difficult_words=json.dumps(merged_words, ensure_ascii=False),
            )
            db.add(row)
            if auto_commit:
                db.commit()
                db.refresh(row)
            else:
                db.flush()
            return UserContext(
                user_id=row.user_id,
                cefr_level=row.cefr_level,
                goals=json.loads(row.goals),
                difficult_words=json.loads(row.difficult_words),
            )

        existing = json.loads(row.difficult_words)
        merged = sorted(set(existing + normalized))
        row.difficult_words = json.dumps(merged, ensure_ascii=False)
        if auto_commit:
            db.commit()
            db.refresh(row)
        else:
            db.flush()
        return UserContext(
            user_id=row.user_id,
            cefr_level=row.cefr_level,
            goals=json.loads(row.goals),
            difficult_words=json.loads(row.difficult_words),
        )

    def update_word_progress(
        self,
        db: Session,
        user_id: int,
        word: str,
        is_correct: bool,
    ) -> WordProgressModel | None:
        normalized = self._normalize_valid_word(word)
        if not normalized:
            return None

        row = db.scalar(
            select(WordProgressModel).where(
                WordProgressModel.user_id == user_id,
                WordProgressModel.word == normalized,
            )
        )
        now = datetime.utcnow()

        if row is None:
            row = WordProgressModel(
                user_id=user_id,
                word=normalized,
                error_count=0,
                correct_streak=0,
                last_reviewed_at=now,
                next_review_at=now,
            )
            db.add(row)
            db.flush()

        row.last_reviewed_at = now
        if is_correct:
            row.correct_streak += 1
            step_idx = min(row.correct_streak - 1, len(self._SRS_STEPS_DAYS) - 1)
            row.next_review_at = now + timedelta(days=self._SRS_STEPS_DAYS[step_idx])
        else:
            row.error_count += 1
            row.correct_streak = 0
            row.next_review_at = now
        return row

    def ensure_word_progress(
        self,
        db: Session,
        user_id: int,
        word: str,
    ) -> WordProgressModel | None:
        normalized = self._normalize_valid_word(word)
        if not normalized:
            return None

        row = db.scalar(
            select(WordProgressModel).where(
                WordProgressModel.user_id == user_id,
                WordProgressModel.word == normalized,
            )
        )
        if row is not None:
            return row

        now = datetime.utcnow()
        row = WordProgressModel(
            user_id=user_id,
            word=normalized,
            error_count=0,
            correct_streak=0,
            last_reviewed_at=now,
            next_review_at=now,
        )
        db.add(row)
        db.flush()
        return row

    def get_word_progress(
        self,
        db: Session,
        user_id: int,
        word: str,
    ) -> WordProgressModel | None:
        normalized = self._normalize_valid_word(word)
        if not normalized:
            return None
        return db.scalar(
            select(WordProgressModel).where(
                WordProgressModel.user_id == user_id,
                WordProgressModel.word == normalized,
            )
        )

    def get_word_progress_map(
        self,
        db: Session,
        user_id: int,
        words: list[str],
    ) -> dict[str, WordProgressModel]:
        normalized = [word for word in (self._normalize_valid_word(item) for item in words) if word]
        if not normalized:
            return {}

        stmt = select(WordProgressModel).where(
            WordProgressModel.user_id == user_id,
            WordProgressModel.word.in_(normalized),
        )
        rows = list(db.scalars(stmt))
        return {row.word: row for row in rows}

    def list_due_word_progress(
        self,
        db: Session,
        user_id: int,
        limit: int,
    ) -> list[WordProgressModel]:
        now = datetime.utcnow()
        stmt = (
            select(WordProgressModel)
            .where(
                WordProgressModel.user_id == user_id,
                WordProgressModel.next_review_at <= now,
            )
            .order_by(WordProgressModel.next_review_at.asc(), WordProgressModel.error_count.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt))

    def count_due_word_progress(
        self,
        db: Session,
        user_id: int,
    ) -> int:
        now = datetime.utcnow()
        stmt = select(func.count(WordProgressModel.id)).where(
            WordProgressModel.user_id == user_id,
            WordProgressModel.next_review_at <= now,
        )
        return int(db.scalar(stmt) or 0)

    def list_upcoming_word_progress(
        self,
        db: Session,
        user_id: int,
        horizon: timedelta,
        limit: int,
    ) -> list[WordProgressModel]:
        now = datetime.utcnow()
        end = now + horizon
        stmt = (
            select(WordProgressModel)
            .where(
                WordProgressModel.user_id == user_id,
                WordProgressModel.next_review_at > now,
                WordProgressModel.next_review_at <= end,
            )
            .order_by(WordProgressModel.next_review_at.asc(), WordProgressModel.error_count.desc())
            .limit(limit)
        )
        return list(db.scalars(stmt))

    def list_word_progress(
        self,
        db: Session,
        user_id: int,
        limit: int,
        offset: int,
        status: Literal["all", "due", "upcoming", "mastered", "troubled"] = "all",
        q: str | None = None,
        sort_by: Literal["next_review_at", "error_count", "correct_streak"] = "next_review_at",
        sort_order: Literal["asc", "desc"] = "asc",
        min_streak: int = 3,
        min_errors: int = 3,
    ) -> list[WordProgressModel]:
        now = datetime.utcnow()
        stmt = select(WordProgressModel).where(WordProgressModel.user_id == user_id)

        if status == "due":
            stmt = stmt.where(WordProgressModel.next_review_at <= now)
        elif status == "upcoming":
            stmt = stmt.where(WordProgressModel.next_review_at > now)
        elif status == "mastered":
            stmt = stmt.where(WordProgressModel.correct_streak >= min_streak)
        elif status == "troubled":
            stmt = stmt.where(WordProgressModel.error_count >= min_errors)

        if q:
            search = q.strip().lower()
            if search:
                stmt = stmt.where(WordProgressModel.word.contains(search))

        if sort_by == "error_count":
            primary_col = WordProgressModel.error_count
        elif sort_by == "correct_streak":
            primary_col = WordProgressModel.correct_streak
        else:
            primary_col = WordProgressModel.next_review_at

        primary_order = asc(primary_col) if sort_order == "asc" else desc(primary_col)
        stmt = stmt.order_by(primary_order, WordProgressModel.next_review_at.asc()).offset(offset).limit(limit)
        return list(db.scalars(stmt))

    def count_word_progress(
        self,
        db: Session,
        user_id: int,
        status: Literal["all", "due", "upcoming", "mastered", "troubled"] = "all",
        q: str | None = None,
        min_streak: int = 3,
        min_errors: int = 3,
    ) -> int:
        now = datetime.utcnow()
        stmt = select(func.count(WordProgressModel.id)).where(WordProgressModel.user_id == user_id)

        if status == "due":
            stmt = stmt.where(WordProgressModel.next_review_at <= now)
        elif status == "upcoming":
            stmt = stmt.where(WordProgressModel.next_review_at > now)
        elif status == "mastered":
            stmt = stmt.where(WordProgressModel.correct_streak >= min_streak)
        elif status == "troubled":
            stmt = stmt.where(WordProgressModel.error_count >= min_errors)

        if q:
            search = q.strip().lower()
            if search:
                stmt = stmt.where(WordProgressModel.word.contains(search))

        return int(db.scalar(stmt) or 0)

    def count_mastered_word_progress(
        self,
        db: Session,
        user_id: int,
        min_streak: int = 3,
    ) -> int:
        stmt = select(func.count(WordProgressModel.id)).where(
            WordProgressModel.user_id == user_id,
            WordProgressModel.correct_streak >= min_streak,
        )
        return int(db.scalar(stmt) or 0)

    def count_troubled_word_progress(
        self,
        db: Session,
        user_id: int,
        min_errors: int = 3,
    ) -> int:
        stmt = select(func.count(WordProgressModel.id)).where(
            WordProgressModel.user_id == user_id,
            WordProgressModel.error_count >= min_errors,
        )
        return int(db.scalar(stmt) or 0)

    def delete_word_progress(
        self,
        db: Session,
        user_id: int,
        word: str,
    ) -> bool:
        normalized = self._normalize_valid_word(word)
        if not normalized:
            return False

        row = db.scalar(
            select(WordProgressModel).where(
                WordProgressModel.user_id == user_id,
                WordProgressModel.word == normalized,
            )
        )
        if row is None:
            return False

        db.delete(row)
        db.flush()
        return True

    def remove_difficult_word(
        self,
        db: Session,
        user_id: int,
        word: str,
    ) -> bool:
        normalized = self._normalize_valid_word(word)
        if not normalized:
            return False

        row = db.get(UserContextModel, user_id)
        if row is None:
            return False

        words = json.loads(row.difficult_words)
        filtered = [item for item in words if item.strip().lower() != normalized]
        if len(filtered) == len(words):
            return False

        row.difficult_words = json.dumps(filtered, ensure_ascii=False)
        db.flush()
        return True

    def cleanup_user_garbage(
        self,
        db: Session,
        user_id: int,
        vocabulary_words: set[str],
    ) -> tuple[int, int]:
        valid_vocabulary = {word for word in vocabulary_words if self._normalize_valid_word(word)}

        removed_word_progress = 0
        progress_rows = list(
            db.scalars(select(WordProgressModel).where(WordProgressModel.user_id == user_id))
        )
        for row in progress_rows:
            normalized = self._normalize_valid_word(row.word)
            if normalized is None or normalized not in valid_vocabulary:
                db.delete(row)
                removed_word_progress += 1

        removed_difficult_words = 0
        context_row = db.get(UserContextModel, user_id)
        if context_row is not None:
            current_words = json.loads(context_row.difficult_words)
            seen: set[str] = set()
            filtered_words: list[str] = []
            for value in current_words:
                normalized = self._normalize_valid_word(value)
                if normalized is None or normalized not in valid_vocabulary:
                    removed_difficult_words += 1
                    continue
                if normalized in seen:
                    removed_difficult_words += 1
                    continue
                seen.add(normalized)
                filtered_words.append(normalized)

            if filtered_words != current_words:
                context_row.difficult_words = json.dumps(filtered_words, ensure_ascii=False)

        db.flush()
        return removed_word_progress, removed_difficult_words


context_repository = ContextMemoryRepository()
