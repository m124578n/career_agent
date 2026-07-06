from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .models import (
    Application, ChatState, CompanyResearch, DismissedInterviews, Interview, InterviewNote, JobPreferences,
    MemoryState, Message, OfferDetail, ResumeState, Settings, Snapshot, TrackedJob, Viewer,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS viewers (
    snapshot_id INTEGER, company TEXT, job_title TEXT, viewed_at TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    snapshot_id INTEGER, job_id TEXT, company TEXT, title TEXT,
    status TEXT, applied_at TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    snapshot_id INTEGER, thread_id TEXT, company TEXT, last_message TEXT,
    has_interview_invite INTEGER, invite_date TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS interviews (
    snapshot_id INTEGER, company TEXT, job_title TEXT, interview_time TEXT,
    location TEXT, status INTEGER, job_url TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resume (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dismissed_interviews (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_research (
    company TEXT PRIMARY KEY, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tracked_jobs (
    code TEXT PRIMARY KEY,
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    salary TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'interested',
    match_score INTEGER,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    match_json TEXT NOT NULL DEFAULT '',
    tailor_json TEXT NOT NULL DEFAULT '',
    offer_json TEXT NOT NULL DEFAULT '',
    interviews_json TEXT NOT NULL DEFAULT ''
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tracked_jobs)")}
    for col in ("match_json", "tailor_json", "offer_json", "interviews_json"):
        if col not in cols:
            conn.execute(f"ALTER TABLE tracked_jobs ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    conn.commit()


def _migrate_preferences(conn: sqlite3.Connection) -> None:
    """把舊 ResumeState 的 target_title/expected_salary 搬進 JobPreferences（冪等、raw-JSON 層）。"""
    res_row = conn.execute("SELECT data FROM resume WHERE id = 1").fetchone()
    if res_row is None:
        return
    resume = json.loads(res_row[0])
    old_title = resume.get("target_title") or ""
    old_salary = resume.get("expected_salary")
    if not old_title and old_salary is None:
        return
    pref_row = conn.execute("SELECT data FROM preferences WHERE id = 1").fetchone()
    prefs = json.loads(pref_row[0]) if pref_row else {}
    changed = False
    if not prefs.get("target_title") and old_title:
        prefs["target_title"] = old_title
        changed = True
    if prefs.get("expected_salary") is None and old_salary is not None:
        prefs["expected_salary"] = old_salary
        changed = True
    if changed:
        conn.execute("INSERT OR REPLACE INTO preferences (id, data) VALUES (1, ?)",
                     (json.dumps(prefs, ensure_ascii=False),))
        conn.commit()


def connect(path: Path | str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    _migrate(conn)
    _migrate_preferences(conn)
    return conn


def save_snapshot(conn: sqlite3.Connection, snapshot: Snapshot, run_at: str) -> int:
    cur = conn.execute("INSERT INTO snapshots (run_at) VALUES (?)", (run_at,))
    sid = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO viewers VALUES (?,?,?,?,?)",
        [(sid, v.company, v.job_title, v.viewed_at, json.dumps(v.raw, ensure_ascii=False)) for v in snapshot.viewers],
    )
    conn.executemany(
        "INSERT INTO applications VALUES (?,?,?,?,?,?,?)",
        [(sid, a.job_id, a.company, a.title, a.status, a.applied_at, json.dumps(a.raw, ensure_ascii=False)) for a in snapshot.applications],
    )
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
        [(sid, m.thread_id, m.company, m.last_message, int(m.has_interview_invite), m.invite_date, json.dumps(m.raw, ensure_ascii=False)) for m in snapshot.messages],
    )
    conn.executemany(
        "INSERT INTO interviews VALUES (?,?,?,?,?,?,?,?)",
        [(sid, iv.company, iv.job_title, iv.when, iv.location, iv.status, iv.job_url, json.dumps(iv.raw, ensure_ascii=False)) for iv in snapshot.interviews],
    )
    conn.commit()
    return sid


def load_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> Snapshot:
    viewers = [
        Viewer(company=c, job_title=t, viewed_at=va, raw=json.loads(rj))
        for c, t, va, rj in conn.execute(
            "SELECT company, job_title, viewed_at, raw_json FROM viewers WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    applications = [
        Application(job_id=j, company=c, title=t, status=s, applied_at=aa, raw=json.loads(rj))
        for j, c, t, s, aa, rj in conn.execute(
            "SELECT job_id, company, title, status, applied_at, raw_json FROM applications WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    messages = [
        Message(thread_id=th, company=c, last_message=lm, has_interview_invite=bool(hi), invite_date=idt, raw=json.loads(rj))
        for th, c, lm, hi, idt, rj in conn.execute(
            "SELECT thread_id, company, last_message, has_interview_invite, invite_date, raw_json FROM messages WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    interviews = [
        Interview(company=c, job_title=t, when=w, location=lo, status=s, job_url=ju, raw=json.loads(rj))
        for c, t, w, lo, s, ju, rj in conn.execute(
            "SELECT company, job_title, interview_time, location, status, job_url, raw_json FROM interviews WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    return Snapshot(viewers=viewers, applications=applications, messages=messages, interviews=interviews)


def latest_two_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 2")]


def latest_run_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT run_at FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None


def _load_single(conn: sqlite3.Connection, table: str, model_cls):
    row = conn.execute(f"SELECT data FROM {table} WHERE id = 1").fetchone()
    return model_cls.model_validate_json(row[0]) if row else model_cls()


def _save_single(conn: sqlite3.Connection, table: str, obj) -> None:
    conn.execute(
        f"INSERT OR REPLACE INTO {table} (id, data) VALUES (1, ?)",
        (obj.model_dump_json(),),
    )
    conn.commit()


def load_chat(conn: sqlite3.Connection) -> ChatState:
    return _load_single(conn, "chat", ChatState)


def save_chat(conn: sqlite3.Connection, state: ChatState) -> None:
    _save_single(conn, "chat", state)


def load_preferences(conn: sqlite3.Connection) -> JobPreferences:
    return _load_single(conn, "preferences", JobPreferences)


def save_preferences(conn: sqlite3.Connection, prefs: JobPreferences) -> None:
    _save_single(conn, "preferences", prefs)


def load_memory(conn: sqlite3.Connection) -> MemoryState:
    return _load_single(conn, "memory", MemoryState)


def save_memory(conn: sqlite3.Connection, mem: MemoryState) -> None:
    _save_single(conn, "memory", mem)


def load_settings(conn: sqlite3.Connection) -> Settings:
    return _load_single(conn, "settings", Settings)


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    _save_single(conn, "settings", settings)


def load_resume(conn: sqlite3.Connection) -> ResumeState:
    return _load_single(conn, "resume", ResumeState)


def save_resume(conn: sqlite3.Connection, state: ResumeState) -> None:
    _save_single(conn, "resume", state)


def load_dismissed(conn: sqlite3.Connection) -> DismissedInterviews:
    return _load_single(conn, "dismissed_interviews", DismissedInterviews)


def save_dismissed(conn: sqlite3.Connection, d: DismissedInterviews) -> None:
    _save_single(conn, "dismissed_interviews", d)


def load_research(conn: sqlite3.Connection, company: str) -> CompanyResearch | None:
    row = conn.execute(
        "SELECT data FROM company_research WHERE company = ?", (company,)
    ).fetchone()
    return CompanyResearch.model_validate_json(row[0]) if row else None


def save_research(conn: sqlite3.Connection, r: CompanyResearch) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO company_research (company, data) VALUES (?, ?)",
        (r.company, r.model_dump_json()),
    )
    conn.commit()


def load_tracked_jobs(conn: sqlite3.Connection) -> list[TrackedJob]:
    rows = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json, interviews_json FROM tracked_jobs ORDER BY updated_at DESC"
    )
    return [
        TrackedJob(
            code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
            match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
            tailor_json=tj or "", offer_json=oj or "", interviews_json=iv or "",
        )
        for c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj, iv in rows
    ]


def get_tracked_job(conn: sqlite3.Connection, code: str) -> TrackedJob | None:
    row = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json, interviews_json FROM tracked_jobs WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        return None
    c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj, iv = row
    return TrackedJob(
        code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
        match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
        tailor_json=tj or "", offer_json=oj or "", interviews_json=iv or "",
    )


def upsert_tracked_job(conn: sqlite3.Connection, job: TrackedJob) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_jobs "
        "(code, company, title, url, salary, state, match_score, created_at, updated_at, match_json, tailor_json, offer_json, interviews_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (job.code, job.company, job.title, job.url, job.salary, job.state,
         job.match_score, job.created_at, job.updated_at, job.match_json, job.tailor_json,
         job.offer_json, job.interviews_json),
    )
    conn.commit()


def delete_tracked_job(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("DELETE FROM tracked_jobs WHERE code = ?", (code,))
    conn.commit()


def merge_tracked_job(
    conn: sqlite3.Connection, code: str, *,
    state: str | None = None, match_score: int | None = None,
    match_json: dict | None = None, tailor_json: dict | None = None,
    company: str = "", title: str = "", url: str = "", salary: str = "",
) -> str:
    """合併 upsert 一筆追蹤職缺：保留 created_at、取較前面狀態、不降級終端、未帶欄位保留舊值。
    match_json/tailor_json 傳 dict 會序列化存入；回最終 state。"""
    from . import pipeline  # 延遲 import 避免與 pipeline 循環
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_tracked_job(conn, code)
    if existing is not None:
        created_at = existing.created_at or now
        if existing.state in pipeline.TERMINAL:
            final_state = existing.state
        elif state is not None and pipeline.STATE_RANK.get(state, 0) >= pipeline.STATE_RANK.get(existing.state, 0):
            final_state = state
        else:
            final_state = existing.state
        new_score = match_score if match_score is not None else existing.match_score
        new_mj = json.dumps(match_json, ensure_ascii=False) if match_json is not None else existing.match_json
        new_tj = json.dumps(tailor_json, ensure_ascii=False) if tailor_json is not None else existing.tailor_json
        new_oj = existing.offer_json
        new_co, new_t, new_u, new_sa = (company or existing.company, title or existing.title,
                                        url or existing.url, salary or existing.salary)
    else:
        created_at = now
        final_state = state or "interested"
        new_score = match_score
        new_mj = json.dumps(match_json, ensure_ascii=False) if match_json is not None else ""
        new_tj = json.dumps(tailor_json, ensure_ascii=False) if tailor_json is not None else ""
        new_oj = ""
        new_co, new_t, new_u, new_sa = company, title, url, salary
    upsert_tracked_job(conn, TrackedJob(
        code=code, company=new_co, title=new_t, url=new_u, salary=new_sa,
        state=final_state, match_score=new_score, created_at=created_at, updated_at=now,
        match_json=new_mj, tailor_json=new_tj, offer_json=new_oj,
    ))
    return final_state


def set_tracked_state(
    conn: sqlite3.Connection, code: str, state: str, *, offer: OfferDetail | None = None,
) -> str:
    """強制設定追蹤職缺狀態（使用者手動；繞過 merge 的 rank 防降級）。
    state=="offer" 且 offer 非 None 時序列化存 offer_json；其餘一律清空 offer_json。
    保留既有 created_at 與其他欄位；不存在則新建。回最終 state。"""
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_tracked_job(conn, code)
    offer_json = (
        json.dumps(offer.model_dump(), ensure_ascii=False)
        if (state == "offer" and offer is not None) else ""
    )
    if existing is not None:
        upsert_tracked_job(conn, TrackedJob(
            code=code, company=existing.company, title=existing.title, url=existing.url,
            salary=existing.salary, state=state, match_score=existing.match_score,
            created_at=existing.created_at or now, updated_at=now,
            match_json=existing.match_json, tailor_json=existing.tailor_json, offer_json=offer_json,
        ))
    else:
        upsert_tracked_job(conn, TrackedJob(
            code=code, state=state, created_at=now, updated_at=now, offer_json=offer_json,
        ))
    return state


def set_interviews(conn: sqlite3.Connection, code: str, notes: list[InterviewNote]) -> None:
    """整列取代某職缺的面試紀錄；不存在則建列；保留其他欄位。"""
    now = datetime.now().isoformat(timespec="seconds")
    interviews_json = json.dumps([n.model_dump() for n in notes], ensure_ascii=False)
    existing = get_tracked_job(conn, code)
    if existing is not None:
        existing.interviews_json = interviews_json
        existing.updated_at = now
        upsert_tracked_job(conn, existing)
    else:
        upsert_tracked_job(conn, TrackedJob(
            code=code, created_at=now, updated_at=now, interviews_json=interviews_json))


def add_interview_note(conn: sqlite3.Connection, code: str, note: InterviewNote) -> None:
    """附加一筆面試紀錄（agent 用）。壞 JSON 視為空列。"""
    existing = get_tracked_job(conn, code)
    notes: list[InterviewNote] = []
    if existing is not None and existing.interviews_json:
        try:
            notes = [InterviewNote.model_validate(x) for x in json.loads(existing.interviews_json)]
        except Exception:
            notes = []
    notes.append(note)
    set_interviews(conn, code, notes)
