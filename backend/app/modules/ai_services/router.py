from fastapi import APIRouter

from app.modules.ai_services.contracts import AIStatusResponse, ExplainErrorRequest, ExplainErrorResponse
from app.modules.ai_services.service import ai_service

router = APIRouter(prefix="/ai", tags=["ai_services"])


@router.post("/explain-error", response_model=ExplainErrorResponse)
async def explain_error(payload: ExplainErrorRequest) -> ExplainErrorResponse:
    return await ai_service.explain_error_async(payload)


@router.get("/status", response_model=AIStatusResponse)
def status() -> AIStatusResponse:
    return ai_service.get_status()
