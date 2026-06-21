"""職缺契合度流程：爬搜尋 + 詳情（節流）→ 逐筆 LLM 分析 → 存 DB → 排序。"""

import httpx

from job_tracker.crawler import crawl_job_details, crawl_jobs
from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import JobMatch, ResumeTarget
from job_tracker.services import job_matching


async def analyze_jobs(
    keyword: str,
    target: ResumeTarget,
    repo: JobRepository,
    *,
    page: int = 1,
    limit: int = 20,
    http_client: httpx.AsyncClient | None = None,
    llm_client=None,
) -> list[JobMatch]:
    """爬一頁職缺（取前 `limit` 筆）→ 抓詳情 → 逐筆契合度分析 → 存 DB，回傳排序結果。"""
    owns_http = http_client is None
    http_client = http_client or httpx.AsyncClient()
    try:
        jobs = (await crawl_jobs(keyword, page=page, client=http_client))[:limit]
        details = await crawl_job_details(
            [job.code for job in jobs], client=http_client
        )

        matches: list[JobMatch] = []
        for job, detail in zip(jobs, details):
            await repo.upsert_job(job)
            await repo.set_detail(job.job_id, detail)
            match = await job_matching.analyze(target, job, detail, client=llm_client)
            await repo.set_match(job.job_id, match)
            matches.append(match)

        return sorted(matches, key=lambda m: m.score, reverse=True)
    finally:
        if owns_http:
            await http_client.aclose()
