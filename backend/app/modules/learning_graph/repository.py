from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Literal
import re
from time import perf_counter

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.learning_graph.observability import learning_graph_observability
from app.modules.learning_graph.models import (
    MistakeEventModel,
    SenseRelationModel,
    TopicClusterModel,
    UserInterestModel,
    VocabularySenseLinkModel,
    WordSenseModel,
)
from app.modules.context_memory.models import WordProgressModel
from app.modules.learning_graph.recommender_strategies import (
    ClusterDeepeningStrategy,
    NeighborExpansionStrategy,
    RecommendationStrategy,
    WeakNodeReinforcementStrategy,
)
from app.modules.learning_graph.schemas import InterestItem, RecommendationItem, SenseAnchorItem


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
    def __init__(self) -> None:
        self._strategies: tuple[RecommendationStrategy, ...] = (
            NeighborExpansionStrategy(),
            ClusterDeepeningStrategy(),
            WeakNodeReinforcementStrategy(),
        )

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

    def _extract_semantic_tokens(self, value: str | None) -> set[str]:
        tokens = {token.lower() for token in self._TAG_WORD_RE.findall(value or "")}
        return {token for token in tokens if len(token) >= 3}

    def _sense_similarity_score(
        self,
        *,
        lemma_a: str,
        translation_a: str,
        context_a: str | None,
        lemma_b: str,
        translation_b: str,
        context_b: str | None,
    ) -> float:
        tokens_a = self._extract_semantic_tokens(f"{lemma_a} {translation_a} {context_a or ''}")
        tokens_b = self._extract_semantic_tokens(f"{lemma_b} {translation_b} {context_b or ''}")
        if not tokens_a or not tokens_b:
            return 0.0
        inter = len(tokens_a & tokens_b)
        if inter == 0:
            return 0.0
        union = len(tokens_a | tokens_b)
        return inter / max(1, union)

    def _pair_ids(self, left_id: int, right_id: int) -> tuple[int, int]:
        return (left_id, right_id) if left_id < right_id else (right_id, left_id)

    def _upsert_relation(
        self,
        db: Session,
        *,
        user_id: int,
        left_sense_id: int,
        right_sense_id: int,
        relation_type: str,
        score: float,
    ) -> None:
        if left_sense_id == right_sense_id:
            return
        left_id, right_id = self._pair_ids(left_sense_id, right_sense_id)
        existing = db.scalar(
            select(SenseRelationModel).where(
                SenseRelationModel.user_id == user_id,
                SenseRelationModel.left_sense_id == left_id,
                SenseRelationModel.right_sense_id == right_id,
            )
        )
        if existing is None:
            db.add(
                SenseRelationModel(
                    user_id=user_id,
                    left_sense_id=left_id,
                    right_sense_id=right_id,
                    relation_type=relation_type,
                    score=round(float(score), 6),
                )
            )
            db.flush()
            return
        if score > existing.score:
            existing.score = round(float(score), 6)
            existing.relation_type = relation_type
            db.flush()

    def _sync_relations_for_sense(
        self,
        db: Session,
        *,
        user_id: int,
        sense: WordSenseModel,
    ) -> None:
        candidates = list(
            db.scalars(
                select(WordSenseModel).where(
                    WordSenseModel.user_id == user_id,
                    WordSenseModel.id != sense.id,
                )
            )
        )
        for candidate in candidates:
            relation_type: str | None = None
            score = 0.0

            if candidate.english_lemma == sense.english_lemma and candidate.semantic_key != sense.semantic_key:
                relation_type = "polysemy_variant"
                score = 0.9
            else:
                semantic_overlap = self._sense_similarity_score(
                    lemma_a=sense.english_lemma,
                    translation_a=sense.russian_translation,
                    context_a=sense.context_definition_ru or sense.source_sentence,
                    lemma_b=candidate.english_lemma,
                    translation_b=candidate.russian_translation,
                    context_b=candidate.context_definition_ru or candidate.source_sentence,
                )
                if semantic_overlap >= 0.2:
                    relation_type = "semantic_overlap"
                    score = semantic_overlap
                elif (
                    sense.topic_cluster_id is not None
                    and candidate.topic_cluster_id is not None
                    and sense.topic_cluster_id == candidate.topic_cluster_id
                ):
                    relation_type = "topic_cluster"
                    score = 0.35

            if relation_type is None:
                continue
            self._upsert_relation(
                db,
                user_id=user_id,
                left_sense_id=sense.id,
                right_sense_id=candidate.id,
                relation_type=relation_type,
                score=score,
            )

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

    def _get_known_lemmas(
        self,
        db: Session,
        *,
        user_id: int,
        min_streak: int = 2,
        max_errors: int = 1,
    ) -> set[str]:
        rows = db.scalars(
            select(WordProgressModel).where(
                WordProgressModel.user_id == user_id,
                WordProgressModel.correct_streak >= min_streak,
                WordProgressModel.error_count <= max_errors,
            )
        )
        return {row.word.strip().lower() for row in rows if row.word}

    def list_interests(self, db: Session, user_id: int) -> list[InterestItem]:
        stmt = (
            select(UserInterestModel)
            .where(UserInterestModel.user_id == user_id)
            .order_by(UserInterestModel.weight.desc(), UserInterestModel.id.asc())
        )
        rows = list(db.scalars(stmt))
        return [InterestItem(interest=row.display_name, weight=row.weight) for row in rows]

    def upsert_interests(self, db: Session, user_id: int, interests: list[InterestItem]) -> list[InterestItem]:
        return self.upsert_interests_with_commit_control(
            db,
            user_id=user_id,
            interests=interests,
            auto_commit=True,
        )

    def upsert_interests_with_commit_control(
        self,
        db: Session,
        *,
        user_id: int,
        interests: list[InterestItem],
        auto_commit: bool,
    ) -> list[InterestItem]:
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
        if auto_commit:
            db.commit()
        else:
            db.flush()
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

        semantic_key = self._normalize_semantic_key(
            f"{translation} {source_sentence or ''} {context_definition_ru or ''}"
        )
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

        self._sync_relations_for_sense(
            db,
            user_id=user_id,
            sense=sense,
        )

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
        relations_count = int(
            db.scalar(
                select(func.count(SenseRelationModel.id)).where(SenseRelationModel.user_id == user_id)
            )
            or 0
        )
        graph_edges_count = links_count + mistakes_count + relations_count

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
            learning_graph_observability.record_recommendation_call(
                user_id=user_id,
                items=[],
                strategy_latencies_ms={},
            )
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

        mistake_counter = Counter(
            row[0]
            for row in db.execute(
                select(MistakeEventModel.english_lemma)
                .where(MistakeEventModel.user_id == user_id, MistakeEventModel.english_lemma.is_not(None))
            )
            if row[0]
        )
        known_lemmas = self._get_known_lemmas(db, user_id=user_id)
        senses_by_id = {sense.id: sense for sense in senses}
        relations = list(
            db.scalars(select(SenseRelationModel).where(SenseRelationModel.user_id == user_id))
        )
        adjacency: dict[int, list[tuple[int, SenseRelationModel]]] = {}
        for relation in relations:
            adjacency.setdefault(relation.left_sense_id, []).append((relation.right_sense_id, relation))
            adjacency.setdefault(relation.right_sense_id, []).append((relation.left_sense_id, relation))

        known_sense_ids = {
            sense.id for sense in senses if sense.english_lemma.strip().lower() in known_lemmas
        }
        mistake_source_ids = {
            sense.id for sense in senses if int(mistake_counter.get(sense.english_lemma.strip().lower(), 0)) > 0
        }
        weak_source_ids = known_sense_ids or mistake_source_ids

        strategy_signals: dict[str, dict[str, float]] = {}
        strategy_latencies_ms: dict[str, float] = {}
        for strategy in self._strategies:
            started_at = perf_counter()
            strategy_signals[strategy.name] = strategy.compute(
                senses=senses,
                clusters=clusters,
                interest_keys=interest_keys,
                known_lemmas=known_lemmas,
                known_sense_ids=known_sense_ids,
                source_sense_ids=weak_source_ids,
                senses_by_id=senses_by_id,
                adjacency=adjacency,
                mistake_counter=mistake_counter,
            )
            strategy_latencies_ms[strategy.name] = (perf_counter() - started_at) * 1000.0

        strategy_weights_by_mode: dict[str, dict[str, float]] = {
            "interest": {
                "ClusterDeepening": 1.0,
                "NeighborExpansion": 0.7,
                "WeakNodeReinforcement": 0.2,
            },
            "weakness": {
                "ClusterDeepening": 0.2,
                "NeighborExpansion": 0.6,
                "WeakNodeReinforcement": 1.0,
            },
            "mixed": {
                "ClusterDeepening": 0.8,
                "NeighborExpansion": 0.8,
                "WeakNodeReinforcement": 1.0,
            },
        }
        strategy_weights = strategy_weights_by_mode.get(mode, strategy_weights_by_mode["mixed"])

        primary_sense_by_lemma: dict[str, WordSenseModel] = {}
        for sense in senses:
            lemma = sense.english_lemma.strip().lower()
            if not lemma:
                continue
            if lemma not in primary_sense_by_lemma:
                primary_sense_by_lemma[lemma] = sense

        weighted_scores: dict[str, float] = {}
        per_strategy_weighted: dict[str, dict[str, float]] = {
            strategy.name: {} for strategy in self._strategies
        }
        reasons_by_lemma: dict[str, set[str]] = {}
        strategy_sources_by_lemma: dict[str, set[str]] = {}

        for strategy_name, signal in strategy_signals.items():
            weight = strategy_weights.get(strategy_name, 0.0)
            if weight <= 0:
                continue
            for lemma, raw_score in signal.items():
                weighted = raw_score * weight
                if weighted <= 0:
                    continue
                weighted_scores[lemma] = weighted_scores.get(lemma, 0.0) + weighted
                per_strategy_weighted[strategy_name][lemma] = weighted
                strategy_sources_by_lemma.setdefault(lemma, set()).add(strategy_name)

        for lemma in list(weighted_scores.keys()):
            mistakes = int(mistake_counter.get(lemma, 0))
            if mistakes > 0 and mode in {"weakness", "mixed"}:
                weighted_scores[lemma] += min(2.0, 0.6 * mistakes)
                reasons_by_lemma.setdefault(lemma, set()).add("mistake_history")
            if lemma in known_lemmas:
                weighted_scores[lemma] *= 0.35
                reasons_by_lemma.setdefault(lemma, set()).add("already_known_penalty")
            if mode == "mixed":
                sources = strategy_sources_by_lemma.get(lemma, set())
                if "ClusterDeepening" in sources and "WeakNodeReinforcement" in sources:
                    weighted_scores[lemma] += 0.5
                    reasons_by_lemma.setdefault(lemma, set()).add("combined_signal")

        items: list[RecommendationItem] = []
        for lemma, total_score in weighted_scores.items():
            if total_score <= 0:
                continue
            sense = primary_sense_by_lemma.get(lemma)
            if sense is None:
                continue
            cluster = clusters.get(sense.topic_cluster_id) if sense.topic_cluster_id else None
            strategy_sources = sorted(strategy_sources_by_lemma.get(lemma, set()))
            if not strategy_sources:
                continue

            primary_strategy = max(
                strategy_sources,
                key=lambda name: per_strategy_weighted.get(name, {}).get(lemma, 0.0),
            )
            reasons = list(reasons_by_lemma.get(lemma, set()))
            reasons.extend(
                [
                    {
                        "NeighborExpansion": "neighbor_expansion",
                        "ClusterDeepening": "interest_match",
                        "WeakNodeReinforcement": "semantic_neighbor",
                    }[strategy]
                    for strategy in strategy_sources
                ]
            )
            # Preserve order while deduping
            seen: set[str] = set()
            reasons_unique: list[str] = []
            for reason in reasons:
                if reason in seen:
                    continue
                seen.add(reason)
                reasons_unique.append(reason)

            items.append(
                RecommendationItem(
                    english_lemma=lemma,
                    russian_translation=sense.russian_translation,
                    topic_cluster=cluster.name if cluster is not None else None,
                    score=round(float(total_score), 4),
                    reasons=reasons_unique,
                    strategy_sources=strategy_sources,
                    primary_strategy=primary_strategy,
                    mistake_count=int(mistake_counter.get(lemma, 0)),
                )
            )

        items.sort(key=lambda row: (row.score, row.mistake_count, row.english_lemma), reverse=True)
        limited = items[:limit]
        learning_graph_observability.record_recommendation_call(
            user_id=user_id,
            items=limited,
            strategy_latencies_ms=strategy_latencies_ms,
        )
        return limited

    def list_anchors(
        self,
        db: Session,
        *,
        user_id: int,
        english_lemma: str,
        limit: int,
    ) -> list[SenseAnchorItem]:
        lemma = self._normalize_lemma(english_lemma)
        if not lemma:
            return []

        source_sense = db.scalar(
            select(WordSenseModel)
            .where(
                WordSenseModel.user_id == user_id,
                WordSenseModel.english_lemma == lemma,
            )
            .order_by(WordSenseModel.id.desc())
        )
        if source_sense is None:
            return []

        relations = list(
            db.scalars(
                select(SenseRelationModel).where(
                    SenseRelationModel.user_id == user_id,
                    or_(
                        SenseRelationModel.left_sense_id == source_sense.id,
                        SenseRelationModel.right_sense_id == source_sense.id,
                    ),
                )
            )
        )
        if not relations:
            return []

        neighbor_ids: set[int] = set()
        for relation in relations:
            if relation.left_sense_id == source_sense.id:
                neighbor_ids.add(relation.right_sense_id)
            else:
                neighbor_ids.add(relation.left_sense_id)
        neighbors = {
            row.id: row
            for row in db.scalars(
                select(WordSenseModel).where(
                    WordSenseModel.user_id == user_id,
                    WordSenseModel.id.in_(neighbor_ids),
                )
            )
        }
        clusters = {
            row.id: row.name
            for row in db.scalars(
                select(TopicClusterModel).where(TopicClusterModel.user_id == user_id)
            )
        }

        anchors: list[SenseAnchorItem] = []
        for relation in relations:
            neighbor_id = (
                relation.right_sense_id if relation.left_sense_id == source_sense.id else relation.left_sense_id
            )
            neighbor = neighbors.get(neighbor_id)
            if neighbor is None:
                continue
            anchors.append(
                SenseAnchorItem(
                    word_sense_id=neighbor.id,
                    english_lemma=neighbor.english_lemma,
                    russian_translation=neighbor.russian_translation,
                    semantic_key=neighbor.semantic_key,
                    relation_type=relation.relation_type,
                    score=round(relation.score, 4),
                    topic_cluster=clusters.get(neighbor.topic_cluster_id) if neighbor.topic_cluster_id else None,
                )
            )

        anchors.sort(key=lambda row: (row.score, row.word_sense_id), reverse=True)
        return anchors[:limit]

    def get_observability(self, *, user_id: int) -> dict[str, object]:
        return learning_graph_observability.get_snapshot(user_id)


learning_graph_repository = LearningGraphRepository()
