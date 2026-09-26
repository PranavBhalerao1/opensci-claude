from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .jobs import mark_interrupted
from .routes import projects


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    mark_interrupted()
    yield


app = FastAPI(title="OpenScientist API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects.router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "models": {
        "reasoning": settings.model_reasoning,
        "standard": settings.model_standard,
        "bulk": settings.model_bulk,
    }}
