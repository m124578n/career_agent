"""104 職缺爬蟲（M4，Playwright）。

MVP：分批抓取（每批 20 筆）以降低被擋風險。
未來考慮：改本機執行 → 經 queue 把結果寫回 DB（見規劃文件未來想法區）。
目前為骨架 stub，待第一週實作。
"""

from job_tracker.schemas import Job


async def crawl_jobs(keyword: str, *, batch: int = 0, size: int = 20) -> list[Job]:
    """以關鍵字搜尋 104，回傳第 `batch` 批（每批 `size` 筆）職缺。

    TODO（第一週）：用 Playwright 實作實際抓取與解析。
    """
    raise NotImplementedError("crawler 待第一週實作（Playwright）")
