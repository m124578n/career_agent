"""104 職缺爬蟲（M4）。

104 有 JSON API，但 WAF 會用 TLS 指紋（JA3）擋掉非瀏覽器的 ClientHello
（Linux/容器的預設 TLS 會被 403）。改用 curl_cffi 模擬 Chrome 的 TLS 指紋，
雲端機房 IP 也能直接取得（實測同機房 IP：httpx 403、curl_cffi 200）。
"""

import asyncio
import logging
import random

from curl_cffi.requests import AsyncSession

from job_tracker.schemas import Job, JobDetail

logger = logging.getLogger("job_tracker.crawler")

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{code}"
WARMUP_URL = "https://www.104.com.tw/jobs/search/"

# curl_cffi 模擬的瀏覽器（連 TLS/JA3 + 預設 header 一起裝成這個版本）
_IMPERSONATE = "chrome"

_SEARCH_HEADERS = {"Referer": WARMUP_URL, "X-Requested-With": "XMLHttpRequest"}


def _new_session() -> AsyncSession:
    return AsyncSession(impersonate=_IMPERSONATE, timeout=30)


async def _warmup(session: AsyncSession) -> None:
    """先載入搜尋頁取得 WAF/session cookie。失敗不擋主流程。"""
    try:
        await session.get(WARMUP_URL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("104 warmup failed (ignored): %s", exc)


async def crawl_jobs(
    keyword: str,
    *,
    page: int = 1,
    area: str | None = None,
    session: AsyncSession | None = None,
) -> list[tuple[Job, bool]]:
    """以關鍵字搜尋 104，回傳指定頁的職缺及是否命中關鍵字。

    `session` 可注入（測試用假 session）；未提供則自建 curl_cffi session 並暖身。
    每筆回傳 (Job, relevant)，relevant 標記是否真正命中關鍵字（104 會夾廣告職缺）。
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
    owns = session is None
    session = session or _new_session()
    try:
        if owns:
            await _warmup(session)
        resp = await session.get(SEARCH_URL, params=params, headers=_SEARCH_HEADERS)
        resp.raise_for_status()
        payload = resp.json()
        out = [
            (_parse_job(raw), _is_relevant(raw, keyword))
            for raw in payload.get("data", [])
        ]
        logger.info("crawl keyword=%r page=%d area=%s -> %d jobs",
                    keyword, page, area, len(out))
        return out
    finally:
        if owns:
            await session.close()


async def fetch_job_detail(
    code: str,
    *,
    session: AsyncSession | None = None,
) -> JobDetail:
    """抓單筆職缺詳情。詳情 API 需帶該職缺自己的 Referer。"""
    headers = {"Referer": f"https://www.104.com.tw/job/{code}"}
    owns = session is None
    session = session or _new_session()
    try:
        if owns:
            await _warmup(session)
        resp = await session.get(DETAIL_URL.format(code=code), headers=headers)
        resp.raise_for_status()
        return parse_job_detail(resp.json())
    finally:
        if owns:
            await session.close()


async def crawl_job_details(
    codes: list[str],
    *,
    session: AsyncSession | None = None,
    min_delay: float = 2.0,
    max_delay: float = 5.0,
) -> list[JobDetail]:
    """逐筆抓多個職缺詳情，請求之間隨機延遲以避免被鎖（反爬節流）。"""
    owns = session is None
    session = session or _new_session()
    results: list[JobDetail] = []
    try:
        if owns:
            await _warmup(session)
        for i, code in enumerate(codes):
            if i > 0:
                await asyncio.sleep(random.uniform(min_delay, max_delay))
            results.append(await fetch_job_detail(code, session=session))
    finally:
        if owns:
            await session.close()
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
