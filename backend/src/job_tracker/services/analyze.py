"""職缺契合度流程：爬搜尋 + 逐筆詳情（節流、容錯）→ LLM 分析 → 存 DB → 排序。

單筆失敗（詳情 403、LLM 偶發解析失敗等）會跳過，不影響整批。
"""

import asyncio
import logging
import random

import httpx

from job_tracker.crawler import crawl_jobs, fetch_job_detail
from job_tracker.db.repositories import JobRepository, MatchRepository
from job_tracker.schemas import JobMatch, ResumeTarget
from job_tracker.services import job_matching

logger = logging.getLogger(__name__)


async def analyze_jobs(
    user: str,
    keyword: str,
    target: ResumeTarget,
    job_repo: JobRepository,
    match_repo: MatchRepository,
    *,
    page: int = 1,
    limit: int = 20,
    http_client: httpx.AsyncClient | None = None,
    llm_client=None,
    min_delay: float = 2.0,
    max_delay: float = 5.0,
) -> list[JobMatch]:
    """爬一頁職缺（取前 `limit` 筆）→ 逐筆分析 → 存（match 按 user 隔離），回傳排序結果。"""
    owns_http = http_client is None
    http_client = http_client or httpx.AsyncClient()
    matches: list[JobMatch] = []
    try:
        jobs = (await crawl_jobs(keyword, page=page, client=http_client))[:limit]
        logger.info(
            "analyze start user=%s keyword=%r limit=%d jobs=%d",
            user,
            keyword,
            limit,
            len(jobs),
        )
        for i, job in enumerate(jobs):
            try:
                if i > 0:  # 請求間節流，避免被鎖
                    await asyncio.sleep(random.uniform(min_delay, max_delay))
                detail = await fetch_job_detail(job.code, client=http_client)
                await job_repo.upsert_job(job)
                await job_repo.set_detail(job.job_id, detail)
                match = await job_matching.analyze(
                    target, job, detail, client=llm_client
                )
                await match_repo.set_match(user, match)
                matches.append(match)
            except Exception:
                logger.warning("跳過分析失敗的職缺 %s", job.job_id, exc_info=True)
                continue

        logger.info("analyze done user=%s -> %d matches", user, len(matches))
        return sorted(matches, key=lambda m: m.score, reverse=True)
    finally:
        if owns_http:
            await http_client.aclose()
