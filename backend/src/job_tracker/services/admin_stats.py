"""admin 營運數據聚合：從既有 collection 統計使用人數/活躍/用量/每日趨勢。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from job_tracker.db.repositories import TokenUsageRepository


class DailyActive(BaseModel):
    day: str
    users: int


class AdminStats(BaseModel):
    total_users: int = 0
    active_7d: int = 0
    active_30d: int = 0
    total_searches: int = 0
    total_analyzed: int = 0
    total_applications: int = 0
    tokens: int = 0
    llm_calls: int = 0
    daily_active: list[DailyActive] = []


async def compute_admin_stats(db) -> AdminStats:
    today = datetime.now(UTC).date()
    cutoff_7 = (today - timedelta(days=6)).isoformat()
    cutoff_30 = (today - timedelta(days=29)).isoformat()

    users_all: set[str] = set()
    users_7: set[str] = set()
    users_30: set[str] = set()
    by_day: dict[str, set[str]] = {}
    async for d in db["daily_usage"].find({}):
        u = d.get("user")
        day = d.get("day")
        if not u or not day:
            continue
        users_all.add(u)
        if day >= cutoff_7:
            users_7.add(u)
        if day >= cutoff_30:
            users_30.add(u)
            by_day.setdefault(day, set()).add(u)

    total_searches = await db["searches"].count_documents({})
    total_analyzed = await db["matches"].count_documents({"status": "done"})
    total_applications = await db["applications"].count_documents({})
    tok = await TokenUsageRepository(db).summary()

    daily = [
        DailyActive(
            day=(day := (today - timedelta(days=i)).isoformat()),
            users=len(by_day.get(day, set())),
        )
        for i in range(29, -1, -1)
    ]

    return AdminStats(
        total_users=len(users_all),
        active_7d=len(users_7),
        active_30d=len(users_30),
        total_searches=total_searches,
        total_analyzed=total_analyzed,
        total_applications=total_applications,
        tokens=tok.get("total_tokens", 0),
        llm_calls=tok.get("calls", 0),
        daily_active=daily,
    )
