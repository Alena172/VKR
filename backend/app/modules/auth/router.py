from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.auth.schemas import (
    LoginOrRegisterRequest,
    LoginOrRegisterResponse,
    TokenIdentityResponse,
    TokenRequest,
    TokenResponse,
    TokenVerifyRequest,
    TokenVerifyResponse,
)
from app.modules.auth.service import auth_service
from app.modules.users.repository import users_repository
from app.modules.users.schemas import UserCreate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
def token(payload: TokenRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = users_repository.get_by_email(db, payload.email)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    token_value = auth_service.create_access_token(user.id)
    return TokenResponse(access_token=token_value, user_id=user.id)


@router.post("/login-or-register", response_model=LoginOrRegisterResponse)
def login_or_register(
    payload: LoginOrRegisterRequest,
    db: Session = Depends(get_db),
) -> LoginOrRegisterResponse:
    user = users_repository.get_by_email(db, payload.email)
    is_new_user = False
    if user is None:
        user = users_repository.create(
            db,
            UserCreate(
                email=payload.email,
                full_name=payload.full_name,
                cefr_level=payload.cefr_level,
            ),
        )
        is_new_user = True

    token_value = auth_service.create_access_token(user.id)
    return LoginOrRegisterResponse(
        access_token=token_value,
        user_id=user.id,
        is_new_user=is_new_user,
    )


@router.post("/verify", response_model=TokenVerifyResponse)
def verify(payload: TokenVerifyRequest) -> TokenVerifyResponse:
    user_id = auth_service.verify_token(payload.token)
    return TokenVerifyResponse(valid=user_id is not None, user_id=user_id)


@router.get("/me", response_model=TokenIdentityResponse)
def me(user_id: int = Depends(get_current_user_id)) -> TokenIdentityResponse:
    return TokenIdentityResponse(user_id=user_id)


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"module": "auth", "status": "ok"}
