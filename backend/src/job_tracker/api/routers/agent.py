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


@router.get("/_diag104")
async def diag_104() -> dict:
    """臨時診斷：從雲端(Zeabur)同時用 httpx(Linux 原生 TLS) 與 curl_cffi(Chrome TLS)
    各抓一次 104，分辨雲端被擋是 IP 還是 TLS 指紋。用完即移除。"""
    import httpx as _httpx
    from curl_cffi.requests import AsyncSession

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    params = {"ro": 0, "keyword": "python", "order": 15, "asc": 0,
              "page": 1, "mode": "s", "jobsource": "index_s"}
    api = "https://www.104.com.tw/jobs/search/api/jobs"
    warm = "https://www.104.com.tw/jobs/search/"
    out: dict = {}

    try:
        async with _httpx.AsyncClient(timeout=15) as c:
            out["egress_ip"] = (await c.get("https://api.ipify.org")).text
    except Exception as e:  # noqa: BLE001
        out["egress_ip"] = f"err: {e}"

    try:
        async with _httpx.AsyncClient(follow_redirects=True, timeout=20) as c:
            await c.get(warm, headers={"User-Agent": UA})
            r = await c.get(api, params=params, headers={
                "User-Agent": UA, "Referer": warm,
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest"})
            out["httpx_status"] = r.status_code
    except Exception as e:  # noqa: BLE001
        out["httpx_status"] = f"err: {type(e).__name__}: {e}"

    try:
        async with AsyncSession(impersonate="chrome", timeout=20) as s:
            await s.get(warm)
            r = await s.get(api, params=params, headers={
                "Referer": warm, "X-Requested-With": "XMLHttpRequest"})
            out["curlcffi_status"] = r.status_code
            try:
                out["curlcffi_count"] = len(r.json().get("data", []))
            except Exception:  # noqa: BLE001
                out["curlcffi_count"] = None
    except Exception as e:  # noqa: BLE001
        out["curlcffi_status"] = f"err: {type(e).__name__}: {e}"

    return out


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
