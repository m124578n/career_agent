"""104 職缺爬蟲（M4）。

實測 104 有 JSON API，帶 Referer header 即可純 HTTP 取得，不需 Playwright。
未來考慮：改本機執行 → 經 queue 把結果寫回 DB（見規劃文件未來想法區）。
"""

import asyncio
import random

import httpx

from job_tracker.schemas import Job, JobDetail

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{code}"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
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


async def fetch_job_detail(
    code: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> JobDetail:
    """抓單筆職缺詳情。詳情 API 需帶該職缺自己的 Referer。"""
    headers = {
        "User-Agent": _UA,
        "Referer": f"https://www.104.com.tw/job/{code}",
        "Accept": "application/json, text/plain, */*",
    }
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        resp = await client.get(DETAIL_URL.format(code=code), headers=headers)
        resp.raise_for_status()
        return parse_job_detail(resp.json())
    finally:
        if owns_client:
            await client.aclose()


async def crawl_job_details(
    codes: list[str],
    *,
    client: httpx.AsyncClient | None = None,
    min_delay: float = 2.0,
    max_delay: float = 5.0,
) -> list[JobDetail]:
    """逐筆抓多個職缺詳情，請求之間隨機延遲以避免被鎖（反爬節流）。"""
    owns_client = client is None
    client = client or httpx.AsyncClient()
    results: list[JobDetail] = []
    try:
        for i, code in enumerate(codes):
            if i > 0:
                await asyncio.sleep(random.uniform(min_delay, max_delay))
            results.append(await fetch_job_detail(code, client=client))
    finally:
        if owns_client:
            await client.aclose()
    return results


def parse_jobs(payload: dict) -> list[Job]:
    """把 104 搜尋 API 的 JSON payload 解析成 Job 清單。"""
    return [_parse_job(raw) for raw in payload.get("data", [])]


def _parse_job(raw: dict) -> Job:
    url = raw["link"]["job"]
    return Job(
        job_id=str(raw["jobNo"]),
        code=url.rstrip("/").rsplit("/", 1)[-1],
        title=raw["jobName"].strip(),
        company=raw["custName"].strip(),
        url=url,
        salary=_format_salary(raw.get("salaryLow", 0), raw.get("salaryHigh", 0)),
        description=raw.get("description", "").strip(),
    )


def _format_salary(low: int, high: int) -> str:
    """salaryLow/High 皆 0 代表面議；否則組成範圍字串。"""
    if not low and not high:
        return "面議"
    return f"{low:,}~{high:,}"


def parse_job_detail(payload: dict) -> JobDetail:
    """把 104 詳情 API 的 JSON payload 解析成 JobDetail。"""
    detail = payload["data"]["jobDetail"]
    cond = payload["data"]["condition"]
    return JobDetail(
        description=detail.get("jobDescription", "").strip(),
        salary=detail.get("salary", ""),
        location=detail.get("addressRegion", ""),
        work_exp=cond.get("workExp", ""),
        education=cond.get("edu", ""),
        majors=list(cond.get("major", [])),
        specialties=[s["description"] for s in cond.get("specialty", [])],
    )
