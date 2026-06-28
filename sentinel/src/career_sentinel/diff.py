from __future__ import annotations

import sqlite3

from . import store
from .models import Diff, Snapshot, StatusChange


def compute_diff(previous: Snapshot | None, current: Snapshot) -> Diff:
    prev = previous or Snapshot()

    prev_viewer_keys = {v.key for v in prev.viewers}
    new_viewers = [v for v in current.viewers if v.key not in prev_viewer_keys]

    prev_apps = {a.job_id: a for a in prev.applications}
    status_changes = [
        StatusChange(application=a, old_status=prev_apps[a.job_id].status, new_status=a.status)
        for a in current.applications
        if a.job_id in prev_apps and prev_apps[a.job_id].status != a.status
    ]

    prev_msgs = {m.thread_id: m for m in prev.messages}
    new_messages = [
        m for m in current.messages
        if m.thread_id not in prev_msgs or prev_msgs[m.thread_id].last_message != m.last_message
    ]
    new_invites = [
        m for m in current.messages
        if m.has_interview_invite
        and (m.thread_id not in prev_msgs or not prev_msgs[m.thread_id].has_interview_invite)
    ]

    return Diff(
        new_viewers=new_viewers,
        status_changes=status_changes,
        new_messages=new_messages,
        new_invites=new_invites,
    )


def diff_against_last(conn: sqlite3.Connection, current_id: int) -> Diff:
    ids = store.latest_two_ids(conn)
    current = store.load_snapshot(conn, current_id)
    previous = None
    for sid in ids:
        if sid != current_id:
            previous = store.load_snapshot(conn, sid)
            break
    return compute_diff(previous, current)
