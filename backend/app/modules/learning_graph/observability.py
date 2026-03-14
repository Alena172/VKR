from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Iterable

from app.modules.learning_graph.schemas import RecommendationItem


@dataclass
class _UserObservabilityState:
    total_requests: int = 0
    empty_requests: int = 0
    weak_requests: int = 0
    total_items: int = 0
    total_top_score: float = 0.0
    total_mean_score: float = 0.0
    primary_strategy_counter: Counter[str] = field(default_factory=Counter)
    latency_samples_ms: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=200)))
    strategy_calls: Counter[str] = field(default_factory=Counter)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _mean(values: Iterable[float]) -> float:
    data = list(values)
    if not data:
        return 0.0
    return sum(data) / len(data)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


class LearningGraphObservability:
    def __init__(self, weak_score_threshold: float = 0.9) -> None:
        self._weak_score_threshold = weak_score_threshold
        self._states: dict[int, _UserObservabilityState] = {}
        self._lock = Lock()

    def _state_for(self, user_id: int) -> _UserObservabilityState:
        return self._states.setdefault(user_id, _UserObservabilityState())

    def record_recommendation_call(
        self,
        *,
        user_id: int,
        items: list[RecommendationItem],
        strategy_latencies_ms: dict[str, float],
    ) -> None:
        with self._lock:
            state = self._state_for(user_id)
            state.total_requests += 1
            state.last_updated = datetime.now(timezone.utc)

            item_count = len(items)
            state.total_items += item_count
            if item_count == 0:
                state.empty_requests += 1
                state.weak_requests += 1
            else:
                top_score = max(float(item.score) for item in items)
                mean_score = sum(float(item.score) for item in items) / item_count
                state.total_top_score += top_score
                state.total_mean_score += mean_score
                if top_score < self._weak_score_threshold:
                    state.weak_requests += 1

            for item in items:
                if item.primary_strategy:
                    state.primary_strategy_counter[item.primary_strategy] += 1

            for strategy_name, latency_ms in strategy_latencies_ms.items():
                latency = max(0.0, float(latency_ms))
                state.latency_samples_ms[strategy_name].append(latency)
                state.strategy_calls[strategy_name] += 1

    def get_snapshot(self, user_id: int) -> dict[str, object]:
        with self._lock:
            state = self._state_for(user_id)
            total = max(1, state.total_requests)

            strategy_latency: list[dict[str, float | int | str]] = []
            for strategy_name, samples in sorted(state.latency_samples_ms.items()):
                values = list(samples)
                strategy_latency.append(
                    {
                        "strategy": strategy_name,
                        "calls": int(state.strategy_calls[strategy_name]),
                        "avg_ms": round(_mean(values), 3),
                        "p95_ms": round(_percentile(values, 0.95), 3),
                        "max_ms": round(max(values) if values else 0.0, 3),
                        "last_ms": round(values[-1] if values else 0.0, 3),
                    }
                )

            primary_strategy_distribution: list[dict[str, float | int | str]] = []
            total_primary = sum(state.primary_strategy_counter.values())
            for strategy_name, count in state.primary_strategy_counter.most_common():
                share = (count / total_primary) if total_primary else 0.0
                primary_strategy_distribution.append(
                    {
                        "strategy": strategy_name,
                        "count": int(count),
                        "share": round(share, 4),
                    }
                )

            return {
                "generated_at": datetime.now(timezone.utc),
                "total_requests": int(state.total_requests),
                "empty_recommendations_share": round(state.empty_requests / total, 4),
                "weak_recommendations_share": round(state.weak_requests / total, 4),
                "avg_items_per_response": round(state.total_items / total, 4),
                "avg_top_score": round(state.total_top_score / total, 4),
                "avg_mean_score": round(state.total_mean_score / total, 4),
                "weak_score_threshold": self._weak_score_threshold,
                "strategy_latency": strategy_latency,
                "primary_strategy_distribution": primary_strategy_distribution,
                "last_updated": state.last_updated,
            }


learning_graph_observability = LearningGraphObservability()
