from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserContextUpsert(BaseModel):
    cefr_level: str = Field(pattern="^(A1|A2|B1|B2|C1|C2)$")
    goals: list[str] = Field(default_factory=list, max_length=10)
    difficult_words: list[str] = Field(default_factory=list, max_length=200)


class UserContext(BaseModel):
    user_id: int
    cefr_level: str
    goals: list[str]
    difficult_words: list[str]


class ContextRecommendations(BaseModel):
    user_id: int
    words: list[str]
    recent_error_words: list[str]
    difficult_words: list[str]
    scores: dict[str, float]
    next_review_at: dict[str, datetime | None]


class ReviewQueueItem(BaseModel):
    word: str
    russian_translation: str | None = None
    next_review_at: datetime
    error_count: int
    correct_streak: int


class ReviewQueueResponse(BaseModel):
    user_id: int
    total_due: int
    items: list[ReviewQueueItem]


class ReviewQueueSubmitRequest(BaseModel):
    word: str = Field(min_length=1, max_length=200)
    is_correct: bool


class ReviewQueueBulkSubmitItem(BaseModel):
    word: str = Field(min_length=1, max_length=200)
    is_correct: bool


class ReviewQueueBulkSubmitRequest(BaseModel):
    items: list[ReviewQueueBulkSubmitItem] = Field(default_factory=list, max_length=200)


class WordProgressRead(BaseModel):
    user_id: int
    word: str
    russian_translation: str | None = None
    error_count: int
    correct_streak: int
    next_review_at: datetime


class WordProgressListResponse(BaseModel):
    user_id: int
    total: int
    limit: int
    offset: int
    items: list[WordProgressRead]


class ReviewQueueBulkSubmitResponse(BaseModel):
    user_id: int
    updated: list[WordProgressRead]


class ReviewPlanResponse(BaseModel):
    user_id: int
    due_count: int
    upcoming_count: int
    due_now: list[ReviewQueueItem]
    upcoming: list[ReviewQueueItem]
    recommended_words: list[str]


class ReviewSessionStartRequest(BaseModel):
    mode: Literal["srs", "random"] = "srs"
    size: int = Field(default=20, ge=1, le=200)


class ReviewSessionItem(BaseModel):
    word: str
    russian_translation: str | None = None
    context_definition: str | None = None
    next_review_at: datetime | None = None
    error_count: int = 0
    correct_streak: int = 0


class ReviewSessionStartResponse(BaseModel):
    user_id: int
    mode: Literal["srs", "random"]
    total_items: int
    items: list[ReviewSessionItem]


class WordProgressDeleteResponse(BaseModel):
    user_id: int
    word: str
    progress_deleted: bool
    removed_from_difficult_words: bool


class ContextGarbageCleanupResponse(BaseModel):
    user_id: int
    removed_word_progress: int
    removed_difficult_words: int


class ProgressSnapshot(BaseModel):
    user_id: int | None = None
    total_sessions: int
    avg_accuracy: float


class ReviewSummary(BaseModel):
    user_id: int
    total_tracked: int
    due_now: int
    mastered: int
    troubled: int
