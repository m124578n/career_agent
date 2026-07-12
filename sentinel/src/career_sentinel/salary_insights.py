"""薪資行情聚合：把 104 搜尋結果的薪資換算月薪、聚合成中位數與分位數。純資料、可單測。"""
from __future__ import annotations

from .models import RecommendedJob, SalaryInsight


def _percentile(sorted_vals: list[int], q: float) -> int | None:
    """線性內插百分位。q 為 0–1。空列回 None。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return int(round(sorted_vals[lo] + (sorted_vals[lo + 1] - sorted_vals[lo]) * frac))
    return sorted_vals[lo]


def compute_salary_insights(keyword: str, jobs: list[RecommendedJob]) -> SalaryInsight:
    reps: list[int] = []
    negotiable = 0
    hourly = 0
    for j in jobs:
        if j.salary_period == "時薪":
            hourly += 1
            continue
        if j.salary_period not in ("月薪", "年薪") or j.salary_low <= 0:
            negotiable += 1
            continue
        ml = j.salary_low if j.salary_period == "月薪" else round(j.salary_low / 12)
        if j.salary_high > 0:
            mh = j.salary_high if j.salary_period == "月薪" else round(j.salary_high / 12)
        else:
            mh = 0
        rep = round((ml + mh) / 2) if mh > 0 else ml
        # rep 為 0 的退化筆（月/年薪但四捨五入後為 0，實務不會發生）直接略過、不計入任何桶
        if rep > 0:
            reps.append(rep)
    if not reps:
        return SalaryInsight(keyword=keyword, sample=0, negotiable=negotiable, hourly_excluded=hourly)
    reps.sort()
    return SalaryInsight(
        keyword=keyword, sample=len(reps), negotiable=negotiable, hourly_excluded=hourly,
        median_monthly=_percentile(reps, 0.5),
        p25_monthly=_percentile(reps, 0.25),
        p75_monthly=_percentile(reps, 0.75),
        min_monthly=reps[0], max_monthly=reps[-1],
    )


def salary_insights_for_keyword(keyword: str, *, pages: int = 3, session=None) -> SalaryInsight:
    """抓 pages 頁 104 搜尋、依 code 去重、聚合。真網路、不單測。"""
    from .scraper.search import fetch_search

    pages = max(1, min(5, pages))
    seen: dict[str, RecommendedJob] = {}
    for p in range(1, pages + 1):
        for j in fetch_search(keyword, page=p, session=session):
            seen.setdefault(j.code, j)
    return compute_salary_insights(keyword, list(seen.values()))
