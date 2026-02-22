"""Prefetch service for exercise generation.

This service pre-generates exercises in the background to reduce latency
when users request new exercises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.modules.exercise_engine.schemas import ExerciseItem


class ExercisePrefetchService:
    """Service for prefetching exercises in the background."""

    def __init__(self) -> None:
        self._queue: dict[tuple[int, str], list[ExerciseItem]] = {}
        self._max_prefetch_per_user = 10

    def has_prefetch(self, user_id: int, mode: str) -> bool:
        """Check if prefetched exercises exist for user."""
        key = (user_id, mode)
        return key in self._queue and len(self._queue[key]) > 0

    def get_prefetched(self, user_id: int, mode: str, count: int) -> list[ExerciseItem]:
        """Get prefetched exercises for user.
        
        Returns up to `count` exercises and removes them from the queue.
        """
        key = (user_id, mode)
        if key not in self._queue:
            return []
        
        exercises = self._queue[key][:count]
        self._queue[key] = self._queue[key][count:]
        
        # Cleanup empty queues
        if not self._queue[key]:
            del self._queue[key]
        
        return exercises

    def store_prefetch(self, user_id: int, mode: str, exercises: list[ExerciseItem]) -> None:
        """Store prefetched exercises for user."""
        key = (user_id, mode)
        if key not in self._queue:
            self._queue[key] = []
        
        # Add new exercises, keeping max limit
        self._queue[key].extend(exercises)
        self._queue[key] = self._queue[key][:self._max_prefetch_per_user]

    def clear_prefetch(self, user_id: int, mode: str | None = None) -> None:
        """Clear prefetched exercises for user."""
        if mode is not None:
            key = (user_id, mode)
            if key in self._queue:
                del self._queue[key]
            return

        to_remove = [key for key in self._queue if key[0] == user_id]
        for key in to_remove:
            del self._queue[key]


# Singleton instance
prefetch_service = ExercisePrefetchService()
