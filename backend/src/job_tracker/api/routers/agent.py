"""本機爬蟲 agent 端點（機器對機器，共享密鑰認證）。

agent 輪詢 claim 認領任務 → 用住宅 IP 抓 104 → complete 回填原始 JSON。
complete 端點依任務型別就地派工：search → 解析存候選；detail → 背景跑 LLM 分析。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from job_tracker.api.deps import (
    get_agent_status_repo, get_analysis_runner, get_crawl_task_repo,
    get_job_repo, get_match_repo, get_quota_repo, get_search_repo, verify_agent,
)
from job_tracker.config import get_settings
from job_tracker.db.repositories import (
    AgentStatusRepository, CrawlTaskRepository, JobRepository,
    MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.services import analyze as analyze_svc
from job_tracker.services.analyze import AnalysisRunner

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(verify_agent)])


class CompleteRequest(BaseModel):
    task_id: str
    raw_json: dict | None = None
    error: str | None = None


@router.post("/claim")
async def claim_task(
    status_repo: AgentStatusRepository = Depends(get_agent_status_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    await status_repo.touch()
    s = get_settings()
    await queue.reap(s.crawl_pending_ttl_sec, s.crawl_claimed_ttl_sec)
    task = await queue.claim()
    return {"task": task.model_dump(mode="json") if task else None}


@router.post("/complete")
async def complete_task(
    req: CompleteRequest,
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
    runner: AnalysisRunner = Depends(get_analysis_runner),
) -> dict:
    if req.error is not None:
        task = await queue.fail(req.task_id, req.error)
        if task and task.type == "search":
            await search_repo.set_crawl_status(task.search_id, "failed")
        elif task and task.job_id:
            await match_repo.set_failed(task.search_id, task.job_id)
        return {"ok": True, "status": "failed"}

    task = await queue.complete(req.task_id, req.raw_json or {})
    if task is None:
        return {"ok": False}
    run = await search_repo.get(task.search_id)
    if task.type == "search":
        cands = await analyze_svc.store_candidates_from_raw(
            task.search_id, task.user, task.payload["keyword"], task.raw_json, match_repo)
        page = task.payload.get("page", 1)
        await search_repo.advance_page(task.search_id, next_page=page + 1, count_delta=len(cands))
        await search_repo.set_crawl_status(task.search_id, "done")
    elif task.type == "detail" and run is not None:
        runner.submit([analyze_svc.analyze_from_detail_raw(
            task.search_id, task.user, task.job_id, task.raw_json,
            run.target, job_repo, match_repo, quota)])
    return {"ok": True, "status": "done"}
