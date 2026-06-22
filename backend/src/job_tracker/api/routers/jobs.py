"""職缺端點：兩階段（爬候選 -> 勾選 -> 非同步逐筆分析）+ 求職信。需登入。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user, ensure_quota, get_analysis_runner, get_job_repo,
    get_match_repo, get_quota_repo, get_search_repo,
)
from job_tracker.config import get_settings
from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.schemas import JobMatch, ResumeTarget, SearchRun
from job_tracker.services import cover_letter as cover_letter_svc
from job_tracker.services.analyze import (
    AnalysisRunner, analyze_one, crawl_candidates,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateSearchRequest(BaseModel):
    keyword: str
    target: ResumeTarget
    area: str | None = None


class AnalyzeRequest(BaseModel):
    job_ids: list[str]


class CoverLetterRequest(BaseModel):
    job_id: str


async def _ensure_owned(search_id, user, search_repo) -> SearchRun:
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
) -> dict:
    run = await search_repo.create(user, req.keyword, req.target, area=req.area)
    cands = await crawl_candidates(run.search_id, user, req.keyword, req.area, 1,
                                   job_repo, match_repo)
    await search_repo.advance_page(run.search_id, next_page=2, count_delta=len(cands))
    return {"search_id": run.search_id, "candidates": [c.model_dump(mode="json") for c in cands]}


@router.post("/searches/{search_id}/crawl-next")
async def crawl_next(
    search_id: str,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> dict:
    run = await _ensure_owned(search_id, user, search_repo)
    cands = await crawl_candidates(search_id, user, run.keyword, run.area, run.next_page,
                                   job_repo, match_repo)
    await search_repo.advance_page(search_id, next_page=run.next_page + 1, count_delta=len(cands))
    return {"candidates": [c.model_dump(mode="json") for c in cands]}


@router.post("/searches/{search_id}/analyze")
async def analyze_selected(
    search_id: str,
    req: AnalyzeRequest,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
    runner: AnalysisRunner = Depends(get_analysis_runner),
) -> dict:
    run = await _ensure_owned(search_id, user, search_repo)
    valid = []
    for jid in req.job_ids:
        m = await match_repo.get_match(search_id, jid)
        # 只收候選或失敗（可重試）的：擋掉 done/pending，
        # 避免重跑已完成的（覆蓋結果、重複計額度）或重複排隊進行中的
        if m is not None and m.status in ("candidate", "failed"):
            valid.append(jid)
    if not valid:
        raise HTTPException(status_code=400, detail="沒有可分析的候選職缺")
    limit = get_settings().daily_call_limit
    if await quota.used_today(user) + len(valid) > limit:
        raise HTTPException(status_code=429, detail=f"今日額度不足（每日 {limit} 次）")
    await match_repo.set_pending(search_id, valid)
    coros = [analyze_one(search_id, user, jid, run.target, job_repo, match_repo, quota)
             for jid in valid]
    runner.submit(coros)
    return {"queued": len(valid)}


@router.get("/searches/{search_id}/matches")
async def search_matches(
    search_id: str,
    user: str = Depends(current_user),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[JobMatch]:
    await _ensure_owned(search_id, user, search_repo)
    return await match_repo.list_by_search(search_id)


@router.get("/searches")
async def list_searches(
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[SearchRun]:
    return await search_repo.list(user)


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
