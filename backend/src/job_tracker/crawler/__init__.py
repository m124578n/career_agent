"""104 職缺爬蟲（M4）。

實測 104 有 JSON API，帶 Referer header 即可純 HTTP 取得，不需 Playwright。
未來考慮：改本機執行 → 經 queue 把結果寫回 DB（見規劃文件未來想法區）。
"""

import asyncio
import logging
import random

import httpx

from job_tracker.schemas import Job, JobDetail

logger = logging.getLogger("job_tracker.crawler")

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{code}"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# 完整 Chrome 請求指紋。機房 IP 會被 104 的 WAF 嚴格檢查，補齊瀏覽器特徵
# 有機會把可疑分數頂過門檻（純 IP 封鎖則無效，需改本機/代理出口）。
_HEADERS = {
    "User-Agent": _UA,
    # 104 沒帶 Referer 會回 403，必要
    "Referer": "https://www.104.com.tw/jobs/search/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# 暖身用：先以瀏覽器姿態載入搜尋頁，取得 WAF/session cookie 再打 API。
_WARMUP_URL = "https://www.104.com.tw/jobs/search/"
_WARMUP_HEADERS = {
    "User-Agent": _UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


async def _warmup(client: httpx.AsyncClient) -> None:
    """先載入搜尋頁取得 cookie（WAF 常要求先有 session）。失敗不擋主流程。"""
    try:
        await client.get(_WARMUP_URL, headers=_WARMUP_HEADERS)
    except httpx.HTTPError as exc:
        logger.warning("104 warmup failed (ignored): %s", exc)


async def crawl_jobs(
    keyword: str,
    *,
    page: int = 1,
    area: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[tuple[Job, bool]]:
    """以關鍵字搜尋 104，回傳指定頁的職缺及是否命中關鍵字。

    `client` 可注入（測試用 MockTransport）；未提供則自建並於結束關閉。
    每筆回傳 (Job, relevant)，relevant 標記該職缺是否真正命中關鍵字
    （104 會夾帶廣告職缺）。
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
    if area:
        params["area"] = area
    owns_client = client is None
    client = client or httpx.AsyncClient(follow_redirects=True)
    try:
        if owns_client:
            await _warmup(client)  # 真實執行先取 cookie；測試注入 client 則跳過
        resp = await client.get(SEARCH_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        payload = resp.json()
        out = parse_search_payload(payload, keyword)
        logger.info("crawl keyword=%r page=%d area=%s -> %d jobs",
                    keyword, page, area, len(out))
        return out
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


def _is_relevant(raw: dict, keyword: str) -> bool:
    """104 會把與關鍵字無關的廣告職缺混入結果。命中關鍵字者 104 會在 snippet
    標 [[[關鍵字]]]；否則退而求其次看關鍵字 token 是否字面出現。"""
    snip = (raw.get("jobNameSnippet", "") or "") + (raw.get("descSnippet", "") or "")
    if "[[[" in snip:
        return True
    tokens = [t for t in keyword.lower().split() if t]
    if not tokens:
        return True
    hay = ((raw.get("jobName", "") or "") + " " + (raw.get("description", "") or "")).lower()
    return any(t in hay for t in tokens)


def parse_search_payload(payload: dict, keyword: str) -> list[tuple[Job, bool]]:
    """把 104 搜尋 API 的原始 JSON 解析成 [(Job, relevant)]。供雲端解析 agent 回傳用。"""
    return [
        (_parse_job(raw), _is_relevant(raw, keyword))
        for raw in payload.get("data", [])
    ]


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


_SALARY_UNBOUNDED = 9999999  # 104 用此值表示「以上」（無上限）


def _format_salary(low: int, high: int) -> str:
    """組薪資字串。皆 0 → 面議；high 為 104 哨兵 → 「X 以上」；否則範圍。"""
    if not low and not high:
        return "面議"
    if high >= _SALARY_UNBOUNDED:
        return f"{low:,} 以上"
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
