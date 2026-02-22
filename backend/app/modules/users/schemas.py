from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=200)
    cefr_level: str = Field(default="A1", pattern="^(A1|A2|B1|B2|C1|C2)$")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None = None
    cefr_level: str
    created_at: datetime
