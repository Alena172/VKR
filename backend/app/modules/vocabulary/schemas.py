from pydantic import BaseModel, ConfigDict, Field

from app.modules.capture.schemas import CaptureItem


class VocabularyItemCreate(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    english_lemma: str = Field(min_length=1, max_length=200)
    russian_translation: str = Field(min_length=1, max_length=200)
    context_definition_ru: str | None = Field(default=None, max_length=3000)
    source_sentence: str | None = Field(default=None, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)


class VocabularyItemCreateMe(BaseModel):
    english_lemma: str = Field(min_length=1, max_length=200)
    russian_translation: str = Field(min_length=1, max_length=200)
    source_sentence: str | None = Field(default=None, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)


class VocabularyItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    english_lemma: str
    russian_translation: str
    context_definition_ru: str | None = None
    source_sentence: str | None = None
    source_url: str | None = None


class VocabularyItemUpdateMe(BaseModel):
    english_lemma: str = Field(min_length=1, max_length=200)
    russian_translation: str = Field(min_length=1, max_length=200)
    source_sentence: str | None = Field(default=None, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)


class VocabularyFromCaptureRequest(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    selected_text: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_sentence: str | None = Field(default=None, max_length=5000)
    force_new_vocabulary_item: bool = False


class VocabularyFromCaptureRequestMe(BaseModel):
    selected_text: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_sentence: str | None = Field(default=None, max_length=5000)
    force_new_vocabulary_item: bool = False


class VocabularyFromCaptureResponse(BaseModel):
    capture: CaptureItem
    vocabulary: VocabularyItem
    translation_note: str
    created_new_vocabulary_item: bool
    queued_for_review: bool
