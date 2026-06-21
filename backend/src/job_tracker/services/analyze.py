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
    offset: int = 0,
    limit: int = 5,
    http_client: httpx.AsyncClient | None = None,
    llm_client=None,
    min_delay: float = 2.0,
    max_delay: float = 5.0,
) -> list[JobMatch]:
    """分析搜尋結果中 [offset, offset+limit) 這批職缺（翻下一批用 offset 累進）。"""
    owns_http = http_client is None
    http_client = http_client or httpx.AsyncClient()
    matches: list[JobMatch] = []
    try:
        # 累積足夠職缺以涵蓋這個視窗（104 每頁約 30 筆；跨頁時多抓幾頁）
        jobs: list = []
        page = 1
        while len(jobs) < offset + limit and page <= 5:
            batch = await crawl_jobs(keyword, page=page, client=http_client)
            if not batch:
                break
            jobs.extend(batch)
            page += 1
        window = jobs[offset : offset + limit]
        logger.info(
            "analyze start user=%s keyword=%r offset=%d limit=%d window=%d",
            user,
            keyword,
            offset,
            limit,
            len(window),
        )
        for i, job in enumerate(window):
            try:
                if i > 0:  # 請求間節流，避免被鎖
                    await asyncio.sleep(random.uniform(min_delay, max_delay))
                detail = await fetch_job_detail(job.code, client=http_client)
                if detail.salary:
                    # 用 104 詳情的完整薪資字串（含 月薪/年薪/以上/面議 等）
                    job.salary = detail.salary
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
