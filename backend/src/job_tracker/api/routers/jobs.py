"""職缺相關端點（M4 爬蟲 + 契合度分析 + 列表）。需登入；分析受每日額度限制。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user,
    ensure_quota,
    get_job_repo,
    get_match_repo,
    get_quota_repo,
)
from job_tracker.db.repositories import JobRepository, MatchRepository, QuotaRepository
from job_tracker.schemas import Job, JobMatch, ResumeTarget
from job_tracker.services.analyze import analyze_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])

_MAX_ANALYZE = 10  # 單次分析上限，避免一次燒太多


class AnalyzeRequest(BaseModel):
    keyword: str
    target: ResumeTarget
    page: int = 1
    limit: int = 5


@router.get("")
async def list_jobs(
    user: str = Depends(current_user),
    repo: JobRepository = Depends(get_job_repo),
) -> list[Job]:
    """列出已抓取的職缺（共用爬取快取）。"""
    return await repo.list_jobs()


@router.get("/matches")
async def list_matches(
    user: str = Depends(current_user),
    match_repo: MatchRepository = Depends(get_match_repo),
) -> list[JobMatch]:
    """列出登入者自己已分析的職缺，依契合度排序。"""
    return await match_repo.list_matches(user)


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> list[JobMatch]:
    """爬取 + 逐筆契合度分析（對標履歷）並存入 DB，回傳排序結果。受每日額度限制。"""
    await ensure_quota(user, quota)
    limit = min(req.limit, _MAX_ANALYZE)
    matches = await analyze_jobs(
        user, req.keyword, req.target, job_repo, match_repo, page=req.page, limit=limit
    )
    await quota.add(user, len(matches))  # 以實際分析筆數計入額度
    return matches
