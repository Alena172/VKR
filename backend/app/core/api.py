from fastapi import APIRouter

from app.modules.ai_services.router import router as ai_services_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.capture.router import router as capture_router
from app.modules.context_memory.router import router as context_memory_router
from app.modules.exercise_engine.router import router as exercise_engine_router
from app.modules.learning_session.router import router as learning_session_router
from app.modules.learning_graph.router import router as learning_graph_router
from app.modules.study_flow.router import router as study_flow_router
from app.modules.translation.router import router as translation_router
from app.modules.users.router import router as users_router
from app.modules.vocabulary.router import router as vocabulary_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(vocabulary_router)
api_router.include_router(capture_router)
api_router.include_router(translation_router)
api_router.include_router(study_flow_router)
api_router.include_router(exercise_engine_router)
api_router.include_router(learning_session_router)
api_router.include_router(learning_graph_router)
api_router.include_router(context_memory_router)
api_router.include_router(analytics_router)
api_router.include_router(ai_services_router)
