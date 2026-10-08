from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import beta
from .auth import CurrentUser, get_current_user
from .config import settings
from .db import init_db
from .jobs import mark_interrupted
from .routes import projects


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    mark_interrupted()
    if settings.gpu_provider == "colab":
        from .execution import colab_runner

        colab_runner.start_reaper()  # stop Colab GPU sessions a previous process left running
    yield


app = FastAPI(title="OpenScientist API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Every product route requires an approved beta account; /api/me below does not, so a
# pending user can still learn their status.
app.include_router(projects.router, dependencies=[Depends(beta.require_approved)])


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "models": {
        "reasoning": settings.model_reasoning,
        "standard": settings.model_standard,
        "bulk": settings.model_bulk,
    }}


@app.get("/api/me")
def me(user: CurrentUser = Depends(get_current_user)) -> dict:
    return {"id": user.id, "email": user.email, **beta.status(user.id)}
