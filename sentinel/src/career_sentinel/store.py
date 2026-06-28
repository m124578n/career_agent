from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Application, Message, Snapshot, Viewer

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
"""


def connect(path: Path | str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
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
    return Snapshot(viewers=viewers, applications=applications, messages=messages)


def latest_two_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 2")]


def latest_run_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT run_at FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None
