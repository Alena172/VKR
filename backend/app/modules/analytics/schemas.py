from pydantic import BaseModel


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
