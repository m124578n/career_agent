"""FastAPI app 進入點。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from job_tracker.api.routers import api_router
from job_tracker.config import get_settings
from job_tracker.db import close_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="104 Job Tracker API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    return app


app = create_app()
