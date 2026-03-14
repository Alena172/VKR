from __future__ import annotations

from collections import Counter, deque
from typing import Protocol

from app.modules.learning_graph.models import SenseRelationModel, TopicClusterModel, WordSenseModel


class RecommendationStrategy(Protocol):
    name: str

    def compute(
        self,
        *,
        senses: list[WordSenseModel],
        clusters: dict[int, TopicClusterModel],
        interest_keys: dict[str, float],
        known_lemmas: set[str],
        known_sense_ids: set[int],
        source_sense_ids: set[int],
        senses_by_id: dict[int, WordSenseModel],
        adjacency: dict[int, list[tuple[int, SenseRelationModel]]],
        mistake_counter: Counter[str],
    ) -> dict[str, float]:
        ...


class NeighborExpansionStrategy:
    name = "NeighborExpansion"

    def compute(
        self,
        *,
        senses: list[WordSenseModel],
        clusters: dict[int, TopicClusterModel],
        interest_keys: dict[str, float],
        known_lemmas: set[str],
        known_sense_ids: set[int],
        source_sense_ids: set[int],
        senses_by_id: dict[int, WordSenseModel],
        adjacency: dict[int, list[tuple[int, SenseRelationModel]]],
        mistake_counter: Counter[str],
    ) -> dict[str, float]:
        if not known_sense_ids:
            return {}

        max_depth = 2
        scores: dict[str, float] = {}
        queue = deque((sense_id, 0) for sense_id in known_sense_ids)
        visited: set[int] = set(known_sense_ids)

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor_id, relation in adjacency.get(current_id, []):
                neighbor = senses_by_id.get(neighbor_id)
                if neighbor is None:
                    continue
                lemma = neighbor.english_lemma.strip().lower()
                if lemma and lemma not in known_lemmas:
                    decay = 1.0 / (depth + 1)
                    boost = max(0.05, relation.score) * decay
                    scores[lemma] = max(scores.get(lemma, 0.0), boost)
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, depth + 1))
        return scores


class ClusterDeepeningStrategy:
    name = "ClusterDeepening"

    def compute(
        self,
        *,
        senses: list[WordSenseModel],
        clusters: dict[int, TopicClusterModel],
        interest_keys: dict[str, float],
        known_lemmas: set[str],
        known_sense_ids: set[int],
        source_sense_ids: set[int],
        senses_by_id: dict[int, WordSenseModel],
        adjacency: dict[int, list[tuple[int, SenseRelationModel]]],
        mistake_counter: Counter[str],
    ) -> dict[str, float]:
        if not interest_keys:
            return {}

        interest_tokens: set[str] = set()
        for key in interest_keys:
            interest_tokens.update(key.split("-"))

        cluster_density = Counter(
            clusters[sense.topic_cluster_id].cluster_key
            for sense in senses
            if sense.topic_cluster_id in clusters
        )
        scores: dict[str, float] = {}
        for sense in senses:
            lemma = sense.english_lemma.strip().lower()
            if not lemma or lemma in known_lemmas:
                continue
            cluster = clusters.get(sense.topic_cluster_id) if sense.topic_cluster_id else None
            if cluster is None:
                continue
            score = 0.0
            if cluster.cluster_key in interest_keys:
                score += 1.8 * interest_keys[cluster.cluster_key]
            if any(token in cluster.cluster_key for token in interest_tokens):
                score += 0.35
            score += min(0.6, 0.08 * cluster_density.get(cluster.cluster_key, 0))
            if score > 0:
                scores[lemma] = max(scores.get(lemma, 0.0), score)
        return scores


class WeakNodeReinforcementStrategy:
    name = "WeakNodeReinforcement"

    def compute(
        self,
        *,
        senses: list[WordSenseModel],
        clusters: dict[int, TopicClusterModel],
        interest_keys: dict[str, float],
        known_lemmas: set[str],
        known_sense_ids: set[int],
        source_sense_ids: set[int],
        senses_by_id: dict[int, WordSenseModel],
        adjacency: dict[int, list[tuple[int, SenseRelationModel]]],
        mistake_counter: Counter[str],
    ) -> dict[str, float]:
        if not source_sense_ids:
            return {}

        weak_edge_max = 0.45
        scores: dict[str, float] = {}
        for source_id in source_sense_ids:
            source = senses_by_id.get(source_id)
            if source is None:
                continue
            source_lemma = source.english_lemma.strip().lower()
            source_mistakes = float(mistake_counter.get(source_lemma, 0))
            for neighbor_id, relation in adjacency.get(source_id, []):
                neighbor = senses_by_id.get(neighbor_id)
                if neighbor is None:
                    continue
                lemma = neighbor.english_lemma.strip().lower()
                if not lemma or lemma in known_lemmas:
                    continue
                if relation.score > weak_edge_max:
                    continue
                weakness = max(0.05, weak_edge_max - relation.score)
                score = weakness + 0.15 * min(4.0, source_mistakes)
                if relation.relation_type == "polysemy_variant":
                    score += 0.15
                scores[lemma] = max(scores.get(lemma, 0.0), score)
        return scores
