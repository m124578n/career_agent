"""職缺擷取流程：爬搜尋 → 存 Job → 抓詳情（節流）→ 存 detail。"""

import httpx

from job_tracker.crawler import crawl_job_details, crawl_jobs
from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import Job


async def ingest_jobs(
    keyword: str,
    repo: JobRepository,
    *,
    page: int = 1,
    fetch_details: bool = True,
    client: httpx.AsyncClient | None = None,
) -> list[Job]:
    """擷取一頁職缺並存入 DB，回傳該頁 Job 清單。

    `fetch_details=True` 時逐筆抓詳情（請求間有節流），存進對應 Job 的 detail。
    """
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        pairs = await crawl_jobs(keyword, page=page, client=client)
        jobs = [job for job, _relevant in pairs]
        for job in jobs:
            await repo.upsert_job(job)

        if fetch_details and jobs:
            details = await crawl_job_details(
                [job.code for job in jobs], client=client
            )
            for job, detail in zip(jobs, details):
                await repo.set_detail(job.job_id, detail)

        return jobs
    finally:
        if owns_client:
            await client.aclose()
