from pydantic import BaseModel, Field


class ExerciseGenerateRequest(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    vocabulary_ids: list[int] = Field(default_factory=list)
    size: int = Field(default=10, ge=1, le=30)
    mode: str = Field(
        default="sentence_translation_full",
        pattern="^(sentence_translation_full|word_definition_match|word_scramble)$",
    )


class ExerciseGenerateRequestMe(BaseModel):
    vocabulary_ids: list[int] = Field(default_factory=list)
    size: int = Field(default=10, ge=1, le=30)
    mode: str = Field(
        default="sentence_translation_full",
        pattern="^(sentence_translation_full|word_definition_match|word_scramble)$",
    )


class ExerciseItem(BaseModel):
    prompt: str
    answer: str
    exercise_type: str
    options: list[str] = Field(default_factory=list)


class ExerciseGenerateResponse(BaseModel):
    exercises: list[ExerciseItem]
    note: str
