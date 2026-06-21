"""把整條求職流程串起來（規劃文件第 2 節的 pipeline）。

上傳履歷 + 目標 → 履歷診斷 → 下關鍵字爬 104（分批）→ 逐筆契合度排序
→ User 決策 → 求職信 / 外部投遞提醒。
"""

from job_tracker.crawler import crawl_job_details, crawl_jobs
from job_tracker.schemas import JobMatch, ResumeTarget
from job_tracker.services import job_matching


async def run_batch(target: ResumeTarget, keyword: str, page: int = 1) -> list[JobMatch]:
    """跑一批：爬一頁職缺 + 詳情（節流）→ 契合度分析排序。"""
    jobs = await crawl_jobs(keyword, page=page)
    details = await crawl_job_details([job.code for job in jobs])
    return await job_matching.analyze_batch(target, list(zip(jobs, details)))
