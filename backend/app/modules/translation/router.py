from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.modules.auth.dependencies import get_current_user_id
from app.modules.ai_services.contracts import TranslateWithContextRequest
from app.modules.ai_services.service import (
    TranslationProviderUnavailableError,
    ai_service,
)
from app.modules.context_memory.repository import context_repository
from app.modules.translation.schemas import TranslateRequest, TranslateRequestMe, TranslateResponse
from app.modules.users.repository import users_repository
from app.modules.vocabulary.repository import vocabulary_repository

router = APIRouter(prefix="/translate", tags=["translation"])


async def _translate_for_user(
    *,
    user_id: int,
    text: str,
    source_context: str | None,
    db: Session,
) -> TranslateResponse:
    user = users_repository.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    context = context_repository.get_by_user_id(db, user_id)
    cefr_level = context.cefr_level if context is not None else user.cefr_level
    vocabulary_items = vocabulary_repository.list_items(db, user_id=user_id)[:50]  # Reduced from 300 to 50

    try:
        ai_response = await ai_service.translate_with_context_async(
            TranslateWithContextRequest(
                text=text,
                cefr_level=cefr_level,
                source_context=source_context,
                glossary=[
                    {
                        "english_term": item.english_lemma,
                        "russian_translation": item.russian_translation,
                        "source_sentence": item.source_sentence,
                    }
                    for item in vocabulary_items
                ],
            )
        )
    except TranslationProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return TranslateResponse(
        translated_text=ai_response.translated_text,
        note=f"AI translation used ({ai_response.provider_note})",
    )


@router.post("/me", response_model=TranslateResponse)
async def translate_me(
    payload: TranslateRequestMe,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> TranslateResponse:
    return await _translate_for_user(
        user_id=current_user_id,
        text=payload.text,
        source_context=payload.source_context,
        db=db,
    )


@router.post("", response_model=TranslateResponse)
async def translate(
    payload: TranslateRequest,
    current_user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> TranslateResponse:
    user_id = payload.user_id or current_user_id
    if user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await _translate_for_user(
        user_id=user_id,
        text=payload.text,
        source_context=payload.source_context,
        db=db,
    )
