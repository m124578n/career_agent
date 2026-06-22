"""職缺端點：搜尋歷史（search runs）+ 契合度分析 + 求職信。需登入、受每日額度限制。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user,
    ensure_quota,
    get_job_repo,
    get_match_repo,
    get_quota_repo,
    get_search_repo,
)
from job_tracker.db.repositories import (
    JobRepository,
    MatchRepository,
    QuotaRepository,
    SearchRepository,
)
from job_tracker.schemas import JobMatch, ResumeTarget, SearchRun
from job_tracker.services import cover_letter as cover_letter_svc
from job_tracker.services.analyze import analyze_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])

_BATCH = 5  # 每批分析筆數


class CreateSearchRequest(BaseModel):
    keyword: str
    target: ResumeTarget


class CoverLetterRequest(BaseModel):
    job_id: str


async def _ensure_owned(search_id: str, user: str, search_repo: SearchRepository) -> SearchRun:
    run = await search_repo.get(search_id)
    if run is None or run.user != user:
        raise HTTPException(status_code=404, detail="找不到該搜尋紀錄")
    return run


@router.post("/searches")
async def create_search(
    req: CreateSearchRequest,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> dict:
    """開一筆新搜尋並分析第一批。"""
    await ensure_quota(user, quota)
    run = await search_repo.create(user, req.keyword, req.target)
    matches = await analyze_jobs(
        run.search_id, user, req.keyword, req.target, job_repo, match_repo,
        offset=0, limit=_BATCH,
    )
    await search_repo.advance(run.search_id, next_offset=_BATCH, count_delta=len(matches))
    await quota.add(user, len(matches))
    return {"search_id": run.search_id, "matches": matches}


@router.post("/searches/{search_id}/next")
async def next_batch(
    search_id: str,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> list[JobMatch]:
    """在既有搜尋上續抓下一批（沿用當時 keyword/target）。"""
    run = await _ensure_owned(search_id, user, search_repo)
    await ensure_quota(user, quota)
    matches = await analyze_jobs(
        run.search_id, user, run.keyword, run.target, job_repo, match_repo,
        offset=run.next_offset, limit=_BATCH,
    )
    await search_repo.advance(
        run.search_id, next_offset=run.next_offset + _BATCH, count_delta=len(matches)
    )
    await quota.add(user, len(matches))
    return matches


@router.get("/searches")
async def list_searches(
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[SearchRun]:
    return await search_repo.list(user)


@router.get("/searches/{search_id}/matches")
async def search_matches(
    search_id: str,
    user: str = Depends(current_user),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[JobMatch]:
    await _ensure_owned(search_id, user, search_repo)
    return await match_repo.list_by_search(search_id)


@router.delete("/searches/{search_id}")
async def delete_search(
    search_id: str,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> dict:
    await _ensure_owned(search_id, user, search_repo)
    await search_repo.delete(search_id)
    return {"ok": True}


@router.post("/searches/{search_id}/cover-letter")
async def generate_cover_letter(
    search_id: str,
    req: CoverLetterRequest,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> dict[str, str]:
    """對該搜尋裡的某職缺生成求職信，存回 match。"""
    run = await _ensure_owned(search_id, user, search_repo)
    match = await match_repo.get_match(search_id, req.job_id)
    if match is None:
        raise HTTPException(status_code=404, detail="找不到該職缺分析")
    await ensure_quota(user, quota)
    detail = await job_repo.get_detail(req.job_id)
    text = await cover_letter_svc.generate(run.target, match.job, detail)
    await match_repo.set_cover_letter(search_id, req.job_id, text)
    await quota.add(user, 1)
    return {"cover_letter": text}
