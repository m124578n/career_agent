from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import calendar_link, company_link, config, diagnosis, diff, digest, jobfetch, match, negotiate, research, resume, store, tailor, usage as usagemod
from ..models import InterviewNote, JobPreferences, OfferDetail, Settings, interview_key
from . import apply, runner, scheduler
from .routers import chat, dashboard, jobs, resume, settings, tracked

logger = logging.getLogger("career_sentinel.web")


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="career-sentinel")
    resolved_db = db_path or str(config.db_path())
    app.state.db_path = resolved_db

    scheduler.start(lambda: store.load_settings(store.connect(resolved_db)))

    app.include_router(settings.router)
    app.include_router(resume.router)
    app.include_router(dashboard.router)
    app.include_router(jobs.router)
    app.include_router(tracked.router)
    app.include_router(chat.router)

    dist = Path(__file__).resolve().parents[3] / "web" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
