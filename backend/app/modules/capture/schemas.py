from pydantic import BaseModel, ConfigDict, Field


class CaptureCreate(BaseModel):
    user_id: int | None = Field(default=None, ge=1)
    selected_text: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_sentence: str | None = Field(default=None, max_length=5000)


class CaptureCreateMe(BaseModel):
    selected_text: str = Field(min_length=1, max_length=2000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_sentence: str | None = Field(default=None, max_length=5000)


class CaptureItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    selected_text: str
    source_url: str | None = None
    source_sentence: str | None = None
