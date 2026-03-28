from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from sqlalchemy.orm import Session

from app.modules.context_memory.repository import context_repository
from app.modules.learning_graph.repository import learning_graph_repository
from app.modules.learning_session.repository import learning_session_repository

_WORD_RE = re.compile(r"^[a-z][a-z'-]{0,48}$")


def _is_valid_review_word(value: str | None) -> bool:
    if not value:
        return False
    return bool(_WORD_RE.fullmatch(value.strip().lower()))


@dataclass
class RecommendationScoreSnapshot:
    scores: dict[str, float]
    recent_error_words_stream: list[str]
    difficult_words: list[str]
    due_progress_map: dict

    def ranked_words(self, limit: int) -> list[str]:
        return [key for key, _ in sorted(self.scores.items(), key=lambda item: item[1], reverse=True)[:limit]]


class RecommendationScoringService:
    def _apply_learning_graph_boost(
        self,
        *,
        db: Session,
        user_id: int,
        scores: dict[str, float],
        limit: int,
    ) -> None:
        graph_items = learning_graph_repository.get_recommendations(
            db,
            user_id=user_id,
            mode="mixed",
            limit=max(limit * 3, 10),
        )
        for rank, item in enumerate(graph_items):
            word = item.english_lemma.strip().lower()
            if not _is_valid_review_word(word):
                continue
            rank_decay = 1.0 / (rank + 1)
            graph_signal = min(6.0, max(0.0, float(item.score)))
            boost = 0.75 * rank_decay + 0.08 * graph_signal
            scores[word] = scores.get(word, 0.0) + boost

    def build_snapshot(
        self,
        *,
        db: Session,
        user_id: int,
        limit: int,
    ) -> RecommendationScoreSnapshot:
        context = context_repository.get_by_user_id(db, user_id)
        difficult_words = [
            word.strip().lower()
            for word in (context.difficult_words if context is not None else [])
            if _is_valid_review_word(word)
        ]
        recent_error_words_stream = learning_session_repository.list_recent_incorrect_words(
            db,
            user_id=user_id,
            limit=limit * 5,
            unique=False,
        )

        scores: dict[str, float] = {}
        for idx, word in enumerate(recent_error_words_stream):
            if not _is_valid_review_word(word):
                continue
            scores[word] = scores.get(word, 0.0) + (1.0 / (idx + 1))

        for word in difficult_words:
            scores[word] = scores.get(word, 0.0) + 0.75

        due_progress_map = context_repository.get_word_progress_map(
            db,
            user_id=user_id,
            words=list(scores.keys()),
        )
        now = datetime.utcnow()
        for word, progress in due_progress_map.items():
            if progress.next_review_at <= now:
                scores[word] = scores.get(word, 0.0) + 1.25

        self._apply_learning_graph_boost(
            db=db,
            user_id=user_id,
            scores=scores,
            limit=limit,
        )

        return RecommendationScoreSnapshot(
            scores=scores,
            recent_error_words_stream=recent_error_words_stream,
            difficult_words=difficult_words,
            due_progress_map=due_progress_map,
        )


recommendation_scoring_service = RecommendationScoringService()
