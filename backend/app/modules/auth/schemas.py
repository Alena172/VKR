from pydantic import BaseModel, EmailStr, Field


class TokenRequest(BaseModel):
    email: EmailStr


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int


class TokenVerifyRequest(BaseModel):
    token: str = Field(min_length=10)


class TokenVerifyResponse(BaseModel):
    valid: bool
    user_id: int | None = None


class TokenIdentityResponse(BaseModel):
    user_id: int


class LoginOrRegisterRequest(BaseModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=200)
    cefr_level: str = Field(default="A1", pattern="^(A1|A2|B1|B2|C1|C2)$")


class LoginOrRegisterResponse(TokenResponse):
    is_new_user: bool
