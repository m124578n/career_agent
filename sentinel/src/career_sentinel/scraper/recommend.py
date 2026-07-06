from __future__ import annotations

from ..models import RecommendedJob

RECOMMEND_URL = "https://www.104.com.tw/api/jobs/personal-recommend-jobs?page=1&pageSize=20"
_HOME = "https://www.104.com.tw/"
_PERIOD = {40: "時薪", 50: "月薪", 60: "年薪"}


def _format_salary(job: dict) -> str:
    low = job.get("salaryLow") or 0
    high = job.get("salaryHigh") or 0
    if job.get("s10") == 10 or (not low and not high):
        return "面議"
    period = _PERIOD.get(job.get("s10"), "月薪")
    if high >= 9999999:
        return f"{period} {low:,} 元以上"
    return f"{period} {low:,}~{high:,} 元"


def parse_recommendations(payload: dict) -> list[RecommendedJob]:
    """把推薦端點 JSON 解析成 RecommendedJob；壞筆（非 dict／缺 jobNo）略過、不炸整批。"""
    out: list[RecommendedJob] = []
    for job in payload.get("data", []) or []:
        if not isinstance(job, dict):
            continue
        code = (job.get("jobNo") or "").strip()
        if not code:
            continue
        link = job.get("link")
        url = (link.get("job") if isinstance(link, dict) else None) or f"https://www.104.com.tw/job/{code}"
        out.append(
            RecommendedJob(
                code=code,
                url=url,
                title=(job.get("jobName") or "").strip(),
                company=(job.get("custName") or "").strip(),
                salary=_format_salary(job),
            )
        )
    return out


def fetch_recommendations(page) -> list[RecommendedJob]:
    """需已登入且已取得 www host 的 Cloudflare clearance。需帶 Referer。需真瀏覽器、不單測。"""
    resp = page.request.get(RECOMMEND_URL, headers={"Referer": _HOME})
    if not resp.ok:
        raise RuntimeError(f"recommend HTTP {resp.status}")
    return parse_recommendations(resp.json())


def recommend_session() -> list[RecommendedJob] | None:
    """開 headful context → 導覽 www 首頁取得 clearance + 確認登入 → 抓推薦。

    未登入回 None（呼叫端提示先 login）。需真瀏覽器、不單測。
    """
    from rebrowser_playwright.sync_api import sync_playwright

    from .. import browser

    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(_HOME, wait_until="domcontentloaded")
            browser.wait_until_ready(page)
            if browser.is_login_url(page.url):
                return None
            return fetch_recommendations(page)
        finally:
            ctx.close()
