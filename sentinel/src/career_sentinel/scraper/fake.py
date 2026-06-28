from __future__ import annotations

from ..models import Application, Message, Snapshot, Viewer


def scrape() -> tuple[Snapshot, set[str]]:
    """本階段假資料；真爬蟲在 scraper/real.py。回 (Snapshot, 空 failed set)。"""
    snapshot = Snapshot(
        viewers=[
            Viewer(company="台積電", job_title="資深後端工程師", viewed_at="2026-06-28 09:12"),
            Viewer(company="聯發科", job_title="平台軟體工程師", viewed_at="2026-06-27 18:40"),
        ],
        applications=[
            Application(job_id="j-1001", company="台積電", title="資深後端工程師", status="邀請面試", applied_at="2026-06-20"),
            Application(job_id="j-1002", company="某新創", title="全端工程師", status="不適合", applied_at="2026-06-18"),
        ],
        messages=[
            Message(thread_id="th-1", company="台積電", last_message="想邀請您本週四面試", has_interview_invite=True, invite_date="2026-07-03"),
            Message(thread_id="th-2", company="某新創", last_message="感謝您的應徵", has_interview_invite=False),
        ],
    )
    return snapshot, set()
