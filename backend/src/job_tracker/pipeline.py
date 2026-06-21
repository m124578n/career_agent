"""把整條求職流程串起來（規劃文件第 2 節的 pipeline）。

上傳履歷 + 目標 → 履歷診斷 → 下關鍵字爬 104（分批）→ 逐筆契合度排序
→ User 決策 → 求職信 / 外部投遞提醒。

目前為流程骨架，各步驟呼叫對應 service；待 service 實作完成後即可端到端跑。
"""

from job_tracker.crawler import crawl_jobs
from job_tracker.schemas import JobMatch, ResumeTarget
from job_tracker.services import job_matching
from job_tracker.services.external_apply import requires_external_apply


async def run_batch(target: ResumeTarget, keyword: str, page: int = 1) -> list[JobMatch]:
    """跑一批：爬一頁職缺 → 契合度分析排序 → 標記外部投遞。"""
    jobs = await crawl_jobs(keyword, page=page)
    matches = await job_matching.match_batch(target, jobs)
    for m in matches:
        m.requires_external_apply = requires_external_apply(m.job.description)
    return matches
