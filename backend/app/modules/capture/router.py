from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.capture.repository import capture_repository
from app.modules.capture.schemas import CaptureCreate, CaptureCreateMe, CaptureItem
from app.modules.users.repository import users_repository

router = APIRouter(prefix="/capture", tags=["capture"])


@router.get("/me", response_model=list[CaptureItem])
def list_my_capture(
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[CaptureItem]:
    return capture_repository.list_items(db, user_id=current_user_id)


@router.get("", response_model=list[CaptureItem])
def list_capture(
    user_id: int | None = Query(default=None, ge=1),
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> list[CaptureItem]:
    if user_id is not None and user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return capture_repository.list_items(db, user_id=user_id or current_user_id)


@router.post("/me", response_model=CaptureItem)
def create_my_capture(
    payload: CaptureCreateMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CaptureItem:
    user = users_repository.get_by_id(db, current_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return capture_repository.create(
        db,
        CaptureCreate(
            user_id=current_user_id,
            selected_text=payload.selected_text,
            source_url=payload.source_url,
            source_sentence=payload.source_sentence,
        ),
    )


@router.post("", response_model=CaptureItem)
def create_capture(
    payload: CaptureCreate,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CaptureItem:
    target_user_id = payload.user_id or current_user_id
    if payload.user_id is not None and payload.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    user = users_repository.get_by_id(db, target_user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return capture_repository.create(
        db,
        payload.model_copy(update={"user_id": target_user_id}),
    )
