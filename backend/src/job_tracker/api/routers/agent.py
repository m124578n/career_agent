"""本機爬蟲 agent 端點（機器對機器，共享密鑰認證）。

agent 輪詢 claim 認領任務 → 用住宅 IP 抓 104 → complete 回填原始 JSON。
complete 的派工處理（解析存候選 / 跑 LLM）在 services 層，見 process_completed_task。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from job_tracker.api.deps import (
    get_agent_status_repo, get_crawl_task_repo, verify_agent,
)
from job_tracker.config import get_settings
from job_tracker.db.repositories import AgentStatusRepository, CrawlTaskRepository

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
) -> dict:
    if req.error is not None:
        await queue.fail(req.task_id, req.error)
        return {"ok": True, "status": "failed"}
    await queue.complete(req.task_id, req.raw_json or {})
    # 解析/LLM 派工在 Task 9 接上
    return {"ok": True, "status": "done"}
