"""職缺契合度流程（兩階段、非同步逐筆）。

爬取：crawl_candidates 抓 104 一頁、存 candidate placeholder。
分析：analyze_one 對單筆抓詳情（經全域 semaphore 節流）→ LLM → 寫結果。
背景執行用可注入的 AnalysisRunner（預設 asyncio.create_task 逐筆序列）。
"""

import asyncio
import logging
from typing import Awaitable, Protocol

from job_tracker.crawler import crawl_jobs, fetch_job_detail
from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository,
)
from job_tracker.schemas import JobMatch, ResumeTarget
from job_tracker.services import job_matching

logger = logging.getLogger(__name__)

# 全域：限制同時對 104 詳情 API 的併發，避免多背景任務一起打被鎖
DETAIL_SEMAPHORE = asyncio.Semaphore(2)


async def crawl_candidates(
    search_id: str,
    user: str,
    keyword: str,
    area: str | None,
    page: int,
    job_repo: JobRepository,
    match_repo: MatchRepository,
) -> list[JobMatch]:
    pairs = await crawl_jobs(keyword, page=page, area=area)
    for job, relevant in pairs:
        await match_repo.add_candidate(search_id, user, job, relevant)
    logger.info("crawl_candidates s=%s page=%d -> %d", search_id, page, len(pairs))
    return [await match_repo.get_match(search_id, j.job_id) for j, _ in pairs]


async def analyze_one(
    search_id: str,
    user: str,
    job_id: str,
    target: ResumeTarget,
    job_repo: JobRepository,
    match_repo: MatchRepository,
    quota: QuotaRepository,
    *,
    llm_client=None,
) -> None:
    try:
        cand = await match_repo.get_match(search_id, job_id)
        if cand is None:
            return
        job = cand.job
        async with DETAIL_SEMAPHORE:
            detail = await fetch_job_detail(job.code)
        if detail.salary:
            job.salary = detail.salary
        await job_repo.upsert_job(job)
        await job_repo.set_detail(job_id, detail)
        analysis = await job_matching.analyze(target, job, detail, client=llm_client)
        await match_repo.set_result(search_id, job_id, analysis)
        await quota.add(user, 1)  # 每筆 done 才計額度
    except Exception:
        logger.warning("分析失敗 job=%s", job_id, exc_info=True)
        await match_repo.set_failed(search_id, job_id)


class AnalysisRunner(Protocol):
    def submit(self, coros: list[Awaitable]) -> None: ...


class AsyncioRunner:
    """預設 runner：背景逐筆序列跑（彼此間靠各自節流 + 全域 semaphore 護 104）。"""

    def __init__(self) -> None:
        # 保存背景 task 引用，避免 fire-and-forget task 被 GC 中途回收（Python 已知陷阱）
        self._tasks: set[asyncio.Task] = set()

    def submit(self, coros: list[Awaitable]) -> None:
        async def _run_all():
            for c in coros:
                await c
        task = asyncio.create_task(_run_all())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
