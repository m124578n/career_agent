"""職缺管道合併引擎（SP15）。

純讀、best-effort：把最新 snapshot 的 applications/interviews 與 tracked_jobs
（手動層）用 104 job code 併成一份 PipelineJob 清單，算出每筆的有效狀態。
任何例外都吞掉回空清單，絕不影響 snapshot / scrape。
"""
from __future__ import annotations

import sqlite3

from . import calendar_link, company_link, jobfetch, store, watch
from .models import PipelineJob, Snapshot, interview_key

STATE_RANK: dict[str, int] = {
    "interested": 1,
    "matched": 2,
    "tailored": 3,
    "applied": 4,
    "interviewing": 5,
}
TERMINAL: set[str] = {"offer", "rejected"}
_RANK_NAME = {r: name for name, r in STATE_RANK.items()}


def effective_state(manual: str | None, signal_rank: int) -> str:
    """manual：tracked_jobs.state（可 None）；signal_rank：104 訊號 rank（0=無）。
    終端手動狀態優先；否則取兩者較前面的狀態名。"""
    if manual in TERMINAL:
        return manual  # type: ignore[return-value]
    manual_rank = STATE_RANK.get(manual or "", 0)
    best = max(manual_rank, signal_rank)
    return _RANK_NAME.get(best, "interested")


def build_pipeline(conn: sqlite3.Connection) -> list[PipelineJob]:
    try:
        return _build(conn)
    except Exception:
        return []


def _build(conn: sqlite3.Connection) -> list[PipelineJob]:
    settings = store.load_settings(conn)
    dismissed = set(store.load_dismissed(conn).keys)
    ids = store.latest_two_ids(conn)
    snap = store.load_snapshot(conn, ids[0]) if ids else Snapshot()

    jobs: dict[str, PipelineJob] = {}
    signal: dict[str, int] = {}  # key -> 104 訊號 rank

    # applications → applied(4)
    for a in snap.applications:
        key = a.job_id or f"app|{a.company}|{a.title}"
        pj = jobs.setdefault(key, PipelineJob(key=key))
        pj.code = a.job_id or pj.code
        pj.company = a.company or pj.company
        pj.title = a.title or pj.title
        pj.status = a.status
        pj.applied_at = a.applied_at
        pj.job_url = company_link.job_url_from_raw(a.raw) or pj.job_url
        pj.company_url = company_link.company_url_from_raw(a.raw) or pj.company_url
        pj.watched = watch.is_watched(a.company, a.title, settings)
        signal[key] = max(signal.get(key, 0), STATE_RANK["applied"])

    # interviews → interviewing(5)
    for iv in snap.interviews:
        try:
            code = jobfetch.extract_job_code(iv.job_url)
        except ValueError:
            code = ""
        key = code or interview_key(iv)
        pj = jobs.setdefault(key, PipelineJob(key=key))
        pj.code = code or pj.code
        pj.company = iv.company or pj.company
        pj.title = iv.job_title or pj.title
        pj.when = iv.when
        pj.location = iv.location
        pj.gcal_link = calendar_link.build_gcal_link(iv)
        pj.interview_key = interview_key(iv)
        pj.dismissed = interview_key(iv) in dismissed
        pj.job_url = iv.job_url or pj.job_url
        pj.company_url = company_link.company_url_from_raw(iv.raw) or pj.company_url
        pj.thread_url = company_link.chat_url_from_raw(iv.raw) or pj.thread_url
        signal[key] = max(signal.get(key, 0), STATE_RANK["interviewing"])

    # tracked_jobs 手動層：併入既有 job 或新增純手動 job
    manual = {tj.code: tj for tj in store.load_tracked_jobs(conn)}
    for key, pj in jobs.items():
        tj = manual.get(pj.code) or manual.get(key)
        if tj is not None:
            pj.url = tj.url or pj.url
            pj.salary = tj.salary or pj.salary
            if tj.match_score is not None:
                pj.match_score = tj.match_score
            pj.company = pj.company or tj.company
            pj.title = pj.title or tj.title
        pj.state = effective_state(tj.state if tj else None, signal.get(key, 0))

    seen_codes = {pj.code for pj in jobs.values() if pj.code}
    for code, tj in manual.items():
        if not code or code in jobs or code in seen_codes:
            continue
        pj = PipelineJob(
            key=code, code=code, company=tj.company, title=tj.title,
            url=tj.url, salary=tj.salary, match_score=tj.match_score,
        )
        pj.state = effective_state(tj.state, 0)
        jobs[code] = pj

    return list(jobs.values())
