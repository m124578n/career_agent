"""dashboard 路由：快照 / 重新抓取 / 狀態 / 用量 / 排程。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ... import calendar_link, company_link, diff, digest, pipeline, stats, store, usage as usagemod, watch
from ...models import interview_key
from ..deps import get_db_path
from .. import runner, scheduler

router = APIRouter()


def _snapshot_payload(conn) -> dict:
    failed = runner.status()["last_failed_readers"]
    try:
        pipeline_jobs = [pj.model_dump() for pj in pipeline.build_pipeline(conn)]
    except Exception:
        pipeline_jobs = []
    try:
        tracked_codes = [tj.code for tj in store.load_tracked_jobs(conn)]
    except Exception:
        tracked_codes = []
    ids = store.latest_two_ids(conn)
    if not ids:
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [], "interviews": [],
            "pipeline": pipeline_jobs,
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": failed,
            "tracked_codes": tracked_codes,
        }
    sid = ids[0]
    snap = store.load_snapshot(conn, sid)
    d = diff.diff_against_last(conn, sid)
    settings = store.load_settings(conn)
    dismissed = set(store.load_dismissed(conn).keys)
    return {
        "run_at": store.latest_run_at(conn),
        "viewers": [{"company": v.company, "job_title": v.job_title, "viewed_at": v.viewed_at, "watched": watch.is_watched(v.company, v.job_title, settings), "company_url": company_link.company_url_from_raw(v.raw)} for v in snap.viewers],
        "applications": [{"job_id": a.job_id, "company": a.company, "title": a.title, "status": a.status, "applied_at": a.applied_at, "watched": watch.is_watched(a.company, a.title, settings), "company_url": company_link.company_url_from_raw(a.raw), "job_url": company_link.job_url_from_raw(a.raw)} for a in snap.applications],
        "messages": [{"thread_id": m.thread_id, "company": m.company, "last_message": m.last_message, "has_interview_invite": m.has_interview_invite, "watched": watch.is_watched(m.company, m.last_message, settings), "company_url": company_link.company_url_from_raw(m.raw), "thread_url": company_link.chat_url_from_raw(m.raw)} for m in snap.messages],
        "interviews": [
            {
                "company": iv.company, "job_title": iv.job_title, "when": iv.when,
                "location": iv.location, "job_url": iv.job_url,
                "gcal_link": calendar_link.build_gcal_link(iv),
                "key": interview_key(iv),
                "dismissed": interview_key(iv) in dismissed,
                "company_url": company_link.company_url_from_raw(iv.raw),
                "thread_url": company_link.chat_url_from_raw(iv.raw),
            }
            for iv in sorted(snap.interviews, key=lambda iv: (iv.when == "", iv.when))
        ],
        "pipeline": pipeline_jobs,
        "digest": digest.render_human(d, snap),
        "failed_readers": failed,
        "tracked_codes": tracked_codes,
    }


@router.get("/api/snapshot")
def snapshot(db_path: str = Depends(get_db_path)) -> dict:
    return _snapshot_payload(store.connect(db_path))


@router.post("/api/scrape")
def scrape(db_path: str = Depends(get_db_path)):
    if not runner.start_scrape(lambda: runner.default_scrape(db_path)):
        return JSONResponse({"status": "already_running"}, status_code=409)
    return {"status": "running"}


@router.get("/api/status")
def status() -> dict:
    return runner.status()


@router.get("/api/usage")
def usage_summary(db_path: str = Depends(get_db_path)) -> dict:
    return usagemod.summary(store.connect(db_path))


@router.delete("/api/usage")
def usage_reset(db_path: str = Depends(get_db_path)) -> dict:
    usagemod.reset(store.connect(db_path))
    return {"status": "reset"}


@router.get("/api/stats")
def stats_ep(db_path: str = Depends(get_db_path)) -> dict:
    return stats.compute_stats(store.connect(db_path)).model_dump()


@router.get("/api/schedule")
def schedule() -> dict:
    return scheduler.state()


@router.post("/api/schedule/ack")
def schedule_ack() -> dict:
    scheduler.ack()
    return {"due": False}
