from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.api import api_router

app = FastAPI(
    title="VKR English Learning API",
    version="0.1.0",
    summary="Modular monolith for RU-native users learning English",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
