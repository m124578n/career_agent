"""104 職缺爬蟲（M4）。

實測 104 有 JSON API，帶 Referer header 即可純 HTTP 取得，不需 Playwright。
未來考慮：改本機執行 → 經 queue 把結果寫回 DB（見規劃文件未來想法區）。
"""

import httpx

from job_tracker.schemas import Job

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    ),
    # 104 沒帶 Referer 會回 403，必要
    "Referer": "https://www.104.com.tw/jobs/search/",
}


async def crawl_jobs(
    keyword: str,
    *,
    page: int = 1,
    client: httpx.AsyncClient | None = None,
) -> list[Job]:
    """以關鍵字搜尋 104，回傳指定頁的職缺。

    `client` 可注入（測試用 MockTransport）；未提供則自建並於結束關閉。
    """
    params = {
        "ro": 0,
        "keyword": keyword,
        "order": 15,  # 依日期新到舊
        "asc": 0,
        "page": page,
        "mode": "s",
        "jobsource": "index_s",
    }
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        resp = await client.get(SEARCH_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        return parse_jobs(resp.json())
    finally:
        if owns_client:
            await client.aclose()


def parse_jobs(payload: dict) -> list[Job]:
    """把 104 搜尋 API 的 JSON payload 解析成 Job 清單。"""
    return [_parse_job(raw) for raw in payload.get("data", [])]


def _parse_job(raw: dict) -> Job:
    return Job(
        job_id=str(raw["jobNo"]),
        title=raw["jobName"].strip(),
        company=raw["custName"].strip(),
        url=raw["link"]["job"],
        salary=_format_salary(raw.get("salaryLow", 0), raw.get("salaryHigh", 0)),
        description=raw.get("description", "").strip(),
    )


def _format_salary(low: int, high: int) -> str:
    """salaryLow/High 皆 0 代表面議；否則組成範圍字串。"""
    if not low and not high:
        return "面議"
    return f"{low:,}~{high:,}"
