"""職缺端點：兩階段（爬候選 -> 勾選 -> 非同步逐筆分析）+ 求職信。需登入。"""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user, ensure_quota, get_agent_status_repo, get_crawl_task_repo,
    get_job_repo, get_match_repo, get_quota_repo, get_search_repo,
)
from job_tracker.config import get_settings
from job_tracker.db.repositories import (
    AgentStatusRepository, CrawlTaskRepository, JobRepository,
    MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.schemas import CrawlTask, JobMatch, ResumeTarget, SearchRun
from job_tracker.services import cover_letter as cover_letter_svc

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
    search_repo: SearchRepository = Depends(get_search_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    run = await search_repo.create(user, req.keyword, req.target, area=req.area)
    await queue.enqueue(CrawlTask(
        task_id=uuid4().hex, type="search",
        payload={"keyword": req.keyword, "page": 1, "area": req.area},
        search_id=run.search_id, user=user))
    return {"search_id": run.search_id, "status": "queued"}


@router.post("/searches/{search_id}/crawl-next")
async def crawl_next(
    search_id: str,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    run = await _ensure_owned(search_id, user, search_repo)
    await search_repo.set_crawl_status(search_id, "queued")
    await queue.enqueue(CrawlTask(
        task_id=uuid4().hex, type="search",
        payload={"keyword": run.keyword, "page": run.next_page, "area": run.area},
        search_id=search_id, user=user))
    return {"status": "queued"}


@router.post("/searches/{search_id}/analyze")
async def analyze_selected(
    search_id: str,
    req: AnalyzeRequest,
    user: str = Depends(current_user),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    await _ensure_owned(search_id, user, search_repo)
    valid = []
    for jid in req.job_ids:
        m = await match_repo.get_match(search_id, jid)
        if m is not None and m.status in ("candidate", "failed"):
            valid.append((jid, m.job.code))
    if not valid:
        raise HTTPException(status_code=400, detail="沒有可分析的候選職缺")
    limit = get_settings().daily_call_limit
    if await quota.used_today(user) + len(valid) > limit:
        raise HTTPException(status_code=429, detail=f"今日額度不足（每日 {limit} 次）")
    await match_repo.set_pending(search_id, [jid for jid, _ in valid])
    for jid, code in valid:
        await queue.enqueue(CrawlTask(
            task_id=uuid4().hex, type="detail", payload={"code": code},
            search_id=search_id, user=user, job_id=jid))
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


@router.get("/searches/{search_id}")
async def get_search(
    search_id: str,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> SearchRun:
    return await _ensure_owned(search_id, user, search_repo)


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


@router.get("/agent-status")
async def agent_status(
    user: str = Depends(current_user),
    status_repo: AgentStatusRepository = Depends(get_agent_status_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    s = get_settings()
    online = await status_repo.is_online(s.agent_offline_after_sec)
    pending = await queue._col.count_documents({"status": {"$in": ["pending", "claimed"]}})
    return {"online": online, "pending": pending}
