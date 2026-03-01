from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.learning_graph.models import (
    MistakeEventModel,
    TopicClusterModel,
    UserInterestModel,
    VocabularySenseLinkModel,
    WordSenseModel,
)
from app.modules.learning_graph.schemas import InterestItem, RecommendationItem


@dataclass
class SemanticUpsertResult:
    sense: WordSenseModel
    created_new: bool
    duplicate_of_id: int | None
    cluster: TopicClusterModel | None


class LearningGraphRepository:
    _WORD_RE = re.compile(r"[^a-z]+")
    _TAG_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z-]{1,32}")

    _TOPIC_HINTS: dict[str, set[str]] = {
        "work": {"work", "office", "meeting", "career", "job", "manager", "team"},
        "study": {"study", "learn", "lesson", "teacher", "student", "exam", "homework"},
        "travel": {"travel", "airport", "hotel", "ticket", "trip", "passport", "train"},
        "shopping": {"shop", "buy", "price", "store", "market", "payment", "order"},
        "daily": {"home", "family", "friend", "food", "time", "day", "today"},
        "it": {"code", "api", "server", "database", "python", "react", "deploy"},
    }

    _MISTAKE_TAG_RULES: list[tuple[str, set[str]]] = [
        ("grammar.tense", {"yesterday", "tomorrow", "ago", "will", "did", "was", "were"}),
        ("grammar.preposition", {"in", "on", "at", "to", "for", "from", "with", "about"}),
        ("syntax.word_order", {"?", "order", "position"}),
        ("lexical.false_friend", {"actual", "fabric", "magazine", "artist"}),
        ("lexical.word_choice", {"choice", "meaning", "context"}),
    ]

    def _normalize_lemma(self, value: str) -> str:
        raw = (value or "").strip().lower()
        if not raw:
            return ""
        return self._WORD_RE.sub("", raw)

    def _normalize_interest_key(self, value: str) -> str:
        tokens = [token.lower() for token in self._TAG_WORD_RE.findall(value or "")]
        if not tokens:
            return ""
        return "-".join(tokens[:3])[:64]

    def _normalize_semantic_key(self, value: str) -> str:
        # Dedup key is intentionally stable and human-readable for demo/debug.
        tokens = [token.lower() for token in self._TAG_WORD_RE.findall(value or "")]
        if not tokens:
            return "generic"
        return "-".join(tokens[:4])[:120]

    def _suggest_cluster_key(
        self,
        *,
        english_lemma: str,
        source_sentence: str | None,
        topic_hint: str | None,
        interest_keys: set[str],
    ) -> str:
        if topic_hint:
            normalized_hint = self._normalize_interest_key(topic_hint)
            if normalized_hint:
                return normalized_hint

        text = f"{english_lemma} {source_sentence or ''}".lower()
        best_key = "daily"
        best_score = 0
        for cluster_key, keywords in self._TOPIC_HINTS.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if cluster_key in interest_keys:
                score += 1
            if score > best_score:
                best_key = cluster_key
                best_score = score
        return best_key

    def _cluster_display_name(self, cluster_key: str) -> str:
        names = {
            "work": "Work & Career",
            "study": "Study",
            "travel": "Travel",
            "shopping": "Shopping",
            "daily": "Daily Life",
            "it": "IT & Tech",
        }
        return names.get(cluster_key, cluster_key.replace("-", " ").title())

    def list_interests(self, db: Session, user_id: int) -> list[InterestItem]:
        stmt = (
            select(UserInterestModel)
            .where(UserInterestModel.user_id == user_id)
            .order_by(UserInterestModel.weight.desc(), UserInterestModel.id.asc())
        )
        rows = list(db.scalars(stmt))
        return [InterestItem(interest=row.display_name, weight=row.weight) for row in rows]

    def upsert_interests(self, db: Session, user_id: int, interests: list[InterestItem]) -> list[InterestItem]:
        db.query(UserInterestModel).filter(UserInterestModel.user_id == user_id).delete()
        for interest in interests:
            key = self._normalize_interest_key(interest.interest)
            if not key:
                continue
            db.add(
                UserInterestModel(
                    user_id=user_id,
                    interest_key=key,
                    display_name=interest.interest.strip(),
                    weight=interest.weight,
                )
            )
        db.commit()
        return self.list_interests(db, user_id)

    def _ensure_cluster(
        self,
        db: Session,
        *,
        user_id: int,
        cluster_key: str,
    ) -> TopicClusterModel:
        row = db.scalar(
            select(TopicClusterModel).where(
                TopicClusterModel.user_id == user_id,
                TopicClusterModel.cluster_key == cluster_key,
            )
        )
        if row is not None:
            return row

        row = TopicClusterModel(
            user_id=user_id,
            cluster_key=cluster_key,
            name=self._cluster_display_name(cluster_key),
            description=f"Auto cluster for '{cluster_key}' context.",
        )
        db.add(row)
        db.flush()
        return row

    def semantic_upsert(
        self,
        db: Session,
        *,
        user_id: int,
        english_lemma: str,
        russian_translation: str,
        context_definition_ru: str | None,
        source_sentence: str | None,
        source_url: str | None,
        topic_hint: str | None = None,
        vocabulary_item_id: int | None = None,
    ) -> SemanticUpsertResult:
        lemma = self._normalize_lemma(english_lemma)
        translation = (russian_translation or "").strip()
        if not lemma or not translation:
            raise ValueError("english_lemma and russian_translation are required")

        semantic_key = self._normalize_semantic_key(translation)
        interest_keys = {
            row.interest_key
            for row in db.scalars(
                select(UserInterestModel).where(UserInterestModel.user_id == user_id)
            )
        }
        cluster_key = self._suggest_cluster_key(
            english_lemma=lemma,
            source_sentence=source_sentence,
            topic_hint=topic_hint,
            interest_keys=interest_keys,
        )
        cluster = self._ensure_cluster(db, user_id=user_id, cluster_key=cluster_key)

        existing = db.scalar(
            select(WordSenseModel).where(
                WordSenseModel.user_id == user_id,
                WordSenseModel.english_lemma == lemma,
                WordSenseModel.semantic_key == semantic_key,
            )
        )

        if existing is not None:
            if vocabulary_item_id is not None:
                link = db.scalar(
                    select(VocabularySenseLinkModel).where(
                        VocabularySenseLinkModel.user_id == user_id,
                        VocabularySenseLinkModel.vocabulary_item_id == vocabulary_item_id,
                    )
                )
                if link is None:
                    db.add(
                        VocabularySenseLinkModel(
                            user_id=user_id,
                            vocabulary_item_id=vocabulary_item_id,
                            word_sense_id=existing.id,
                        )
                    )
                    db.flush()
            return SemanticUpsertResult(
                sense=existing,
                created_new=False,
                duplicate_of_id=existing.id,
                cluster=cluster,
            )

        sense = WordSenseModel(
            user_id=user_id,
            english_lemma=lemma,
            semantic_key=semantic_key,
            russian_translation=translation,
            context_definition_ru=context_definition_ru,
            source_sentence=source_sentence,
            source_url=source_url,
            topic_cluster_id=cluster.id,
        )
        db.add(sense)
        db.flush()

        if vocabulary_item_id is not None:
            db.add(
                VocabularySenseLinkModel(
                    user_id=user_id,
                    vocabulary_item_id=vocabulary_item_id,
                    word_sense_id=sense.id,
                )
            )
            db.flush()

        return SemanticUpsertResult(
            sense=sense,
            created_new=True,
            duplicate_of_id=None,
            cluster=cluster,
        )

    def _classify_mistake_tag(
        self,
        *,
        prompt: str | None,
        expected_answer: str | None,
        user_answer: str | None,
    ) -> str:
        text = f"{prompt or ''} {expected_answer or ''} {user_answer or ''}".lower()
        for tag, markers in self._MISTAKE_TAG_RULES:
            if any(marker in text for marker in markers):
                return tag
        if len((expected_answer or "").split()) > 4:
            return "syntax.phrase_building"
        return "lexical.translation"

    def add_mistake_event(
        self,
        db: Session,
        *,
        user_id: int,
        english_lemma: str | None,
        prompt: str | None,
        expected_answer: str | None,
        user_answer: str | None,
        session_id: int | None = None,
    ) -> MistakeEventModel:
        lemma = self._normalize_lemma(english_lemma or "")
        sense = None
        if lemma:
            sense = db.scalar(
                select(WordSenseModel)
                .where(
                    WordSenseModel.user_id == user_id,
                    WordSenseModel.english_lemma == lemma,
                )
                .order_by(WordSenseModel.id.desc())
            )
        tag = self._classify_mistake_tag(
            prompt=prompt,
            expected_answer=expected_answer,
            user_answer=user_answer,
        )
        row = MistakeEventModel(
            user_id=user_id,
            session_id=session_id,
            english_lemma=lemma or None,
            word_sense_id=sense.id if sense is not None else None,
            mistake_tag=tag,
            prompt=prompt,
            expected_answer=expected_answer,
            user_answer=user_answer,
        )
        db.add(row)
        db.flush()
        return row

    def get_overview(
        self,
        db: Session,
        *,
        user_id: int,
    ) -> dict[str, int | list[str]]:
        interests_count = int(
            db.scalar(select(func.count(UserInterestModel.id)).where(UserInterestModel.user_id == user_id)) or 0
        )
        clusters_count = int(
            db.scalar(select(func.count(TopicClusterModel.id)).where(TopicClusterModel.user_id == user_id)) or 0
        )
        senses_count = int(
            db.scalar(select(func.count(WordSenseModel.id)).where(WordSenseModel.user_id == user_id)) or 0
        )
        mistakes_count = int(
            db.scalar(select(func.count(MistakeEventModel.id)).where(MistakeEventModel.user_id == user_id)) or 0
        )
        links_count = int(
            db.scalar(
                select(func.count(VocabularySenseLinkModel.id)).where(VocabularySenseLinkModel.user_id == user_id)
            )
            or 0
        )
        graph_edges_count = links_count + mistakes_count

        top_interests_rows = list(
            db.execute(
                select(UserInterestModel.display_name)
                .where(UserInterestModel.user_id == user_id)
                .order_by(UserInterestModel.weight.desc(), UserInterestModel.id.asc())
                .limit(5)
            )
        )
        top_interests = [row[0] for row in top_interests_rows]

        top_clusters_rows = list(
            db.execute(
                select(TopicClusterModel.name, func.count(WordSenseModel.id))
                .join(WordSenseModel, WordSenseModel.topic_cluster_id == TopicClusterModel.id)
                .where(TopicClusterModel.user_id == user_id, WordSenseModel.user_id == user_id)
                .group_by(TopicClusterModel.id)
                .order_by(func.count(WordSenseModel.id).desc(), TopicClusterModel.id.asc())
                .limit(5)
            )
        )
        top_clusters = [row[0] for row in top_clusters_rows]

        top_tags_rows = list(
            db.execute(
                select(MistakeEventModel.mistake_tag, func.count(MistakeEventModel.id))
                .where(MistakeEventModel.user_id == user_id)
                .group_by(MistakeEventModel.mistake_tag)
                .order_by(func.count(MistakeEventModel.id).desc(), MistakeEventModel.mistake_tag.asc())
                .limit(5)
            )
        )
        top_tags = [row[0] for row in top_tags_rows]

        return {
            "interests_count": interests_count,
            "topic_clusters_count": clusters_count,
            "word_senses_count": senses_count,
            "mistake_events_count": mistakes_count,
            "graph_edges_count": graph_edges_count,
            "top_interests": top_interests,
            "top_clusters": top_clusters,
            "top_mistake_tags": top_tags,
        }

    def get_recommendations(
        self,
        db: Session,
        *,
        user_id: int,
        mode: Literal["interest", "weakness", "mixed"],
        limit: int,
    ) -> list[RecommendationItem]:
        senses = list(
            db.scalars(
                select(WordSenseModel)
                .where(WordSenseModel.user_id == user_id)
                .order_by(WordSenseModel.id.desc())
            )
        )
        if not senses:
            return []

        clusters = {
            row.id: row
            for row in db.scalars(select(TopicClusterModel).where(TopicClusterModel.user_id == user_id))
        }
        interests = list(
            db.scalars(
                select(UserInterestModel).where(UserInterestModel.user_id == user_id).order_by(UserInterestModel.weight.desc())
            )
        )
        interest_keys = {item.interest_key: item.weight for item in interests}
        interest_tokens = set()
        for key in interest_keys:
            interest_tokens.update(key.split("-"))

        mistake_counter = Counter(
            row[0]
            for row in db.execute(
                select(MistakeEventModel.english_lemma)
                .where(MistakeEventModel.user_id == user_id, MistakeEventModel.english_lemma.is_not(None))
            )
            if row[0]
        )

        best_by_lemma: dict[str, RecommendationItem] = {}
        for sense in senses:
            cluster = clusters.get(sense.topic_cluster_id) if sense.topic_cluster_id else None
            cluster_key = cluster.cluster_key if cluster is not None else ""
            score = 0.0
            reasons: list[str] = []
            mistake_count = int(mistake_counter.get(sense.english_lemma, 0))

            if mode in {"interest", "mixed"}:
                interest_score = 0.0
                if cluster_key in interest_keys:
                    interest_score += 2.5 * interest_keys[cluster_key]
                if cluster_key and any(token in cluster_key for token in interest_tokens):
                    interest_score += 0.8
                if interest_score > 0:
                    score += interest_score
                    reasons.append("interest_match")

            if mode in {"weakness", "mixed"} and mistake_count > 0:
                weakness_score = min(8.0, 1.3 * mistake_count)
                score += weakness_score
                reasons.append("mistake_history")

            if mode == "mixed" and score > 0 and cluster_key in interest_keys and mistake_count > 0:
                score += 0.8
                reasons.append("combined_signal")

            if score <= 0:
                continue

            item = RecommendationItem(
                english_lemma=sense.english_lemma,
                russian_translation=sense.russian_translation,
                topic_cluster=cluster.name if cluster is not None else None,
                score=round(score, 4),
                reasons=reasons,
                mistake_count=mistake_count,
            )
            existing = best_by_lemma.get(item.english_lemma)
            if existing is None or item.score > existing.score:
                best_by_lemma[item.english_lemma] = item

        ranked = sorted(
            best_by_lemma.values(),
            key=lambda row: (row.score, row.mistake_count, row.english_lemma),
            reverse=True,
        )
        return ranked[:limit]


learning_graph_repository = LearningGraphRepository()
