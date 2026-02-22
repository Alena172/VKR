from pydantic import BaseModel, Field


class TranslateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    user_id: int | None = Field(default=None, ge=1)
    source_context: str | None = Field(default=None, max_length=10000)


class TranslateRequestMe(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    source_context: str | None = Field(default=None, max_length=10000)


class TranslateResponse(BaseModel):
    translated_text: str
    note: str
