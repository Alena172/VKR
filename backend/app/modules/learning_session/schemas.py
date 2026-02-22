from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionAnswer(BaseModel):
    exercise_id: int = Field(ge=1)
    prompt: str | None = Field(default=None, max_length=2000)
    expected_answer: str | None = Field(default=None, max_length=1000)
    user_answer: str = Field(min_length=1, max_length=1000)
    is_correct: bool | None = None


class SessionSubmitRequest(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    answers: list[SessionAnswer] = Field(default_factory=list)


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    total: int
    correct: int
    accuracy: float
    created_at: datetime


class SessionHistoryResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SessionSummary]


class SessionAnswerFeedback(BaseModel):
    exercise_id: int
    explanation_ru: str


class SessionSubmitResponse(BaseModel):
    session: SessionSummary
    incorrect_feedback: list[SessionAnswerFeedback] = Field(default_factory=list)


class SessionAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    exercise_id: int
    prompt: str | None = None
    expected_answer: str | None = None
    user_answer: str
    is_correct: bool
    explanation_ru: str | None = None
