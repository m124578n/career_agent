"""FastAPI app 進入點。"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from job_tracker import llm
from job_tracker.api.routers import agent as agent_router
from job_tracker.api.routers import api_router
from job_tracker.config import get_settings
from job_tracker.db import close_client, get_db
from job_tracker.db.repositories import TokenUsageRepository
from job_tracker.llm import usage as llm_usage
from job_tracker.logging_config import setup_logging

logger = logging.getLogger("job_tracker.app")
request_logger = logging.getLogger("job_tracker.request")


async def _mongo_usage_sink(rec: dict) -> None:
    await TokenUsageRepository(get_db()).record(rec)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    llm_usage.set_sink(_mongo_usage_sink)  # token 用量寫進 Mongo
    logger.info(
        "app start | llm=%s db=%s", llm.describe(), settings.mongo_db
    )
    yield
    llm_usage.set_sink(None)
    await close_client()
    logger.info("app stop")


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="104 Job Tracker API", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        dur = time.perf_counter() - start
        request_logger.info(
            "%s %s %s %.2fs",
            request.method,
            request.url.path,
            response.status_code,
            dur,
        )
        return response

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(api_router)
    app.include_router(agent_router.router, prefix="/api")
    return app


app = create_app()
