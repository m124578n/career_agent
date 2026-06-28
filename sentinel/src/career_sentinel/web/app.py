from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import config, diff, digest, store
from . import runner


def _snapshot_payload(conn) -> dict:
    ids = store.latest_two_ids(conn)
    if not ids:
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [],
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": runner.status()["last_failed_readers"],
        }
    sid = ids[0]
    snap = store.load_snapshot(conn, sid)
    d = diff.diff_against_last(conn, sid)
    return {
        "run_at": store.latest_run_at(conn),
        "viewers": [{"company": v.company, "job_title": v.job_title, "viewed_at": v.viewed_at} for v in snap.viewers],
        "applications": [{"job_id": a.job_id, "company": a.company, "title": a.title, "status": a.status, "applied_at": a.applied_at} for a in snap.applications],
        "messages": [{"thread_id": m.thread_id, "company": m.company, "last_message": m.last_message, "has_interview_invite": m.has_interview_invite} for m in snap.messages],
        "digest": digest.render_human(d, snap),
        "failed_readers": runner.status()["last_failed_readers"],
    }


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="career-sentinel")

    def _conn():
        return store.connect(db_path or str(config.db_path()))

    @app.get("/api/snapshot")
    def snapshot() -> dict:
        return _snapshot_payload(_conn())

    @app.post("/api/scrape")
    def scrape():
        if not runner.start_scrape(runner.default_scrape):
            return JSONResponse({"status": "already_running"}, status_code=409)
        return {"status": "running"}

    @app.get("/api/status")
    def status() -> dict:
        return runner.status()

    dist = Path(__file__).resolve().parents[3] / "web" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
