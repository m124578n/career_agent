from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config, diagnosis, diff, digest, resume, store, watch
from ..models import ResumeState, Settings
from . import runner


class _DiagnoseReq(BaseModel):
    target_title: str
    expected_salary: int | None = None


def _snapshot_payload(conn) -> dict:
    failed = runner.status()["last_failed_readers"]
    ids = store.latest_two_ids(conn)
    if not ids:
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [],
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": failed,
        }
    sid = ids[0]
    snap = store.load_snapshot(conn, sid)
    d = diff.diff_against_last(conn, sid)
    settings = store.load_settings(conn)
    return {
        "run_at": store.latest_run_at(conn),
        "viewers": [{"company": v.company, "job_title": v.job_title, "viewed_at": v.viewed_at, "watched": watch.is_watched(v.company, v.job_title, settings)} for v in snap.viewers],
        "applications": [{"job_id": a.job_id, "company": a.company, "title": a.title, "status": a.status, "applied_at": a.applied_at, "watched": watch.is_watched(a.company, a.title, settings)} for a in snap.applications],
        "messages": [{"thread_id": m.thread_id, "company": m.company, "last_message": m.last_message, "has_interview_invite": m.has_interview_invite, "watched": watch.is_watched(m.company, m.last_message, settings)} for m in snap.messages],
        "digest": digest.render_human(d, snap),
        "failed_readers": failed,
    }


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="career-sentinel")
    resolved_db = db_path or str(config.db_path())

    def _conn():
        return store.connect(resolved_db)

    @app.get("/api/snapshot")
    def snapshot() -> dict:
        return _snapshot_payload(_conn())

    @app.post("/api/scrape")
    def scrape():
        if not runner.start_scrape(lambda: runner.default_scrape(resolved_db)):
            return JSONResponse({"status": "already_running"}, status_code=409)
        return {"status": "running"}

    @app.get("/api/status")
    def status() -> dict:
        return runner.status()

    @app.get("/api/settings")
    def get_settings() -> dict:
        return store.load_settings(_conn()).model_dump()

    @app.put("/api/settings")
    def put_settings(settings: Settings) -> dict:
        store.save_settings(_conn(), settings)
        return settings.model_dump()

    @app.post("/api/resume/upload")
    async def resume_upload(file: UploadFile = File(...)) -> dict:
        data = await file.read()
        try:
            text = resume.parse_resume(file.filename or "resume", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conn = _conn()
        state = store.load_resume(conn)
        state.resume_text = text
        store.save_resume(conn, state)
        return {"chars": len(text)}

    @app.post("/api/resume/diagnose")
    def resume_diagnose(req: _DiagnoseReq) -> dict:
        conn = _conn()
        state = store.load_resume(conn)
        if not state.resume_text.strip():
            raise HTTPException(status_code=400, detail="請先上傳履歷")
        try:
            result = diagnosis.diagnose(state.resume_text, req.target_title, req.expected_salary)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="健檢失敗，請重試")
        state.target_title = req.target_title
        state.expected_salary = req.expected_salary
        state.diagnosis = result
        store.save_resume(conn, state)
        return result.model_dump()

    @app.get("/api/resume")
    def resume_get() -> dict:
        state = store.load_resume(_conn())
        return {
            "has_resume": bool(state.resume_text.strip()),
            "chars": len(state.resume_text),
            "target_title": state.target_title,
            "expected_salary": state.expected_salary,
            "diagnosis": state.diagnosis.model_dump() if state.diagnosis else None,
        }

    dist = Path(__file__).resolve().parents[3] / "web" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
