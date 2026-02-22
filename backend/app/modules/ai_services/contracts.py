from pydantic import BaseModel, Field


class ExplainErrorRequest(BaseModel):
    english_prompt: str = Field(min_length=1, max_length=2000)
    user_answer: str = Field(min_length=1, max_length=1000)
    expected_answer: str = Field(min_length=1, max_length=1000)


class ExplainErrorResponse(BaseModel):
    explanation_ru: str


class TranslateGlossaryItem(BaseModel):
    english_term: str = Field(min_length=1, max_length=200)
    russian_translation: str = Field(min_length=1, max_length=200)
    source_sentence: str | None = Field(default=None, max_length=2000)


class TranslateWithContextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    cefr_level: str | None = Field(default=None, pattern="^(A1|A2|B1|B2|C1|C2)$")
    source_context: str | None = Field(default=None, max_length=10000)
    glossary: list[TranslateGlossaryItem] = Field(default_factory=list)


class TranslateWithContextResponse(BaseModel):
    translated_text: str
    provider_note: str


class ExerciseSeed(BaseModel):
    english_lemma: str = Field(min_length=1, max_length=200)
    russian_translation: str = Field(min_length=1, max_length=200)
    source_sentence: str | None = Field(default=None, max_length=2000)


class GenerateExercisesRequest(BaseModel):
    size: int = Field(ge=1, le=30)
    cefr_level: str | None = Field(default=None, pattern="^(A1|A2|B1|B2|C1|C2)$")
    mode: str = Field(
        default="sentence_translation_full",
        pattern="^(sentence_translation_full|word_definition_match|word_scramble)$",
    )
    seeds: list[ExerciseSeed] = Field(default_factory=list)


class GeneratedExerciseItem(BaseModel):
    prompt: str
    answer: str
    exercise_type: str
    options: list[str] = Field(default_factory=list)


class GenerateExercisesResponse(BaseModel):
    exercises: list[GeneratedExerciseItem]
    provider_note: str


class AIStatusResponse(BaseModel):
    provider: str
    model: str
    remote_enabled: bool
    base_url: str
    timeout_seconds: float
    max_retries: int
