from pydantic import BaseModel, Field

from app.modules.capture.schemas import CaptureItem
from app.modules.vocabulary.schemas import VocabularyItem


class CaptureToVocabularyRequest(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    selected_text: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_sentence: str | None = Field(default=None, max_length=5000)
    force_new_vocabulary_item: bool = False


class CaptureToVocabularyRequestMe(BaseModel):
    selected_text: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_sentence: str | None = Field(default=None, max_length=5000)
    force_new_vocabulary_item: bool = False


class CaptureToVocabularyResponse(BaseModel):
    capture: CaptureItem
    vocabulary: VocabularyItem
    translation_note: str
    created_new_vocabulary_item: bool
    queued_for_review: bool
