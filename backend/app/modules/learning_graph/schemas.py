from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InterestItem(BaseModel):
    interest: str = Field(min_length=1, max_length=120)
    weight: float = Field(default=1.0, ge=0.1, le=10.0)


class InterestUpsertRequest(BaseModel):
    interests: list[InterestItem] = Field(default_factory=list, max_length=30)


class TopicClusterRead(BaseModel):
    id: int
    key: str
    name: str
    description: str | None = None


class UserInterestsResponse(BaseModel):
    user_id: int
    interests: list[InterestItem]


class SemanticUpsertRequest(BaseModel):
    english_lemma: str = Field(min_length=1, max_length=200)
    russian_translation: str = Field(min_length=1, max_length=200)
    context_definition_ru: str | None = Field(default=None, max_length=3000)
    source_sentence: str | None = Field(default=None, max_length=5000)
    source_url: str | None = Field(default=None, max_length=2000)
    topic_hint: str | None = Field(default=None, max_length=120)
    vocabulary_item_id: int | None = Field(default=None, ge=1)


class WordSenseRead(BaseModel):
    id: int
    english_lemma: str
    semantic_key: str
    russian_translation: str
    context_definition_ru: str | None = None
    source_sentence: str | None = None
    source_url: str | None = None
    topic_cluster_id: int | None = None
    created_at: datetime


class SemanticUpsertResponse(BaseModel):
    user_id: int
    created_new_sense: bool
    semantic_duplicate_of_id: int | None = None
    sense: WordSenseRead
    cluster: TopicClusterRead | None = None


class LearningGraphOverviewResponse(BaseModel):
    user_id: int
    interests_count: int
    topic_clusters_count: int
    word_senses_count: int
    mistake_events_count: int
    graph_edges_count: int
    top_interests: list[str]
    top_clusters: list[str]
    top_mistake_tags: list[str]


class RecommendationItem(BaseModel):
    english_lemma: str
    russian_translation: str
    topic_cluster: str | None = None
    score: float
    reasons: list[str]
    mistake_count: int


class RecommendationsResponse(BaseModel):
    user_id: int
    mode: Literal["interest", "weakness", "mixed"]
    items: list[RecommendationItem]
