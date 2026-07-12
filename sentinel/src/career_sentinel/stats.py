"""求職統計聚合：漏斗（累積達到）、轉換率、各階段停留、停滯提醒。純資料、可單測。"""
from __future__ import annotations

from datetime import datetime
from statistics import median

from pydantic import BaseModel

from . import pipeline, store

STALE_DAYS = 14

_LABELS: dict[str, str] = {
    "interested": "有興趣", "matched": "已比對", "tailored": "已客製化",
    "applied": "已投遞", "interviewing": "面試中", "offer": "offer", "rejected": "未錄取",
}
_FUNNEL_ORDER = ["interested", "matched", "tailored", "applied", "interviewing", "offer"]
_DWELL_STATES = ["interested", "matched", "tailored", "offer", "rejected"]
# offer 視為 6（高於 interviewing 的 5）；rejected 不參與 reached
_RANK = {"interested": 1, "matched": 2, "tailored": 3, "applied": 4, "interviewing": 5, "offer": 6}


class FunnelStage(BaseModel):
    state: str
    label: str
    count: int


class Conversions(BaseModel):
    applied_to_interview: int | None = None
    interview_to_offer: int | None = None
    interested_to_offer: int | None = None


class DwellStat(BaseModel):
    state: str
    label: str
    median_days: int | None
    sample: int


class StaleJob(BaseModel):
    code: str
    company: str
    title: str
    state: str
    label: str
    days_since_update: int
    url: str


class StatsResult(BaseModel):
    funnel: list[FunnelStage]
    rejected_count: int
    conversions: Conversions
    dwell: list[DwellStat]
    stale: list[StaleJob]


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _pct(n: int, d: int) -> int | None:
    return None if d == 0 else round(100 * n / d)


def compute_stats(conn) -> StatsResult:
    jobs = pipeline.build_pipeline(conn)
    ranks = [_RANK.get(j.state, 0) for j in jobs if j.state != "rejected"]

    def reached(state: str) -> int:
        return sum(1 for r in ranks if r >= _RANK[state])

    funnel = [FunnelStage(state=s, label=_LABELS[s], count=reached(s)) for s in _FUNNEL_ORDER]
    rejected_count = sum(1 for j in jobs if j.state == "rejected")
    conversions = Conversions(
        applied_to_interview=_pct(reached("interviewing"), reached("applied")),
        interview_to_offer=_pct(reached("offer"), reached("interviewing")),
        interested_to_offer=_pct(reached("offer"), reached("interested")),
    )

    # 停留：依 code 分組事件時間軸，每段 = 下一事件 − 本事件（現階段 = now − 本事件）
    now = datetime.now()
    by_code: dict[str, list] = {}
    for e in store.load_state_events(conn):
        by_code.setdefault(e.code, []).append(e)
    samples: dict[str, list[int]] = {s: [] for s in _DWELL_STATES}
    for evs in by_code.values():
        for i, e in enumerate(evs):
            start = _parse(e.at)
            if start is None:
                continue
            end = _parse(evs[i + 1].at) if i + 1 < len(evs) else now
            if end is None:
                continue
            days = (end - start).days
            if e.state in samples and days >= 0:
                samples[e.state].append(days)
    dwell = [
        DwellStat(
            state=s, label=_LABELS[s],
            median_days=(int(median(samples[s])) if samples[s] else None),
            sample=len(samples[s]),
        )
        for s in _DWELL_STATES
    ]

    # 停滯：非終端、距 updated_at > STALE_DAYS
    stale: list[StaleJob] = []
    for t in store.load_tracked_jobs(conn):
        if t.state in pipeline.TERMINAL:
            continue
        upd = _parse(t.updated_at)
        if upd is None:
            continue
        days = (now - upd).days
        if days > STALE_DAYS:
            stale.append(StaleJob(
                code=t.code, company=t.company, title=t.title, state=t.state,
                label=_LABELS.get(t.state, t.state), days_since_update=days, url=t.url,
            ))
    stale.sort(key=lambda j: j.days_since_update, reverse=True)

    return StatsResult(funnel=funnel, rejected_count=rejected_count,
                       conversions=conversions, dwell=dwell, stale=stale)
