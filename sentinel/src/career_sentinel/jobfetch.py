from __future__ import annotations

import re

from .models import JobDetail

_DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{code}"
_WARMUP_URL = "https://www.104.com.tw/jobs/search/"
_CODE_RE = re.compile(r"104\.com\.tw/job/([^/?#]+)")


def extract_job_code(url: str) -> str:
    """從 104 職缺網址取 code（/job/{code}）。非 104 職缺網址 raise ValueError。"""
    m = _CODE_RE.search(url or "")
    if not m:
        raise ValueError("請貼 104 職缺網址")
    return m.group(1)


def parse_job_detail(payload: dict) -> JobDetail:
    """把 104 詳情 API 的 JSON 解析成 JobDetail。"""
    data = payload.get("data", {}) or {}
    header = data.get("header", {}) or {}
    jd = data.get("jobDetail", {}) or {}
    cond = data.get("condition", {}) or {}
    return JobDetail(
        title=(header.get("jobName") or "").strip(),
        company=(header.get("custName") or "").strip(),
        salary=jd.get("salary", "") or "",
        location=jd.get("addressRegion", "") or "",
        description=(jd.get("jobDescription") or "").strip(),
        work_exp=cond.get("workExp", "") or "",
        education=cond.get("edu", "") or "",
        majors=list(cond.get("major", []) or []),
        specialties=[s.get("description", "") for s in (cond.get("specialty", []) or [])],
    )


def fetch_job_detail(code: str, *, session=None) -> JobDetail:
    """curl_cffi 抓 104 公開職缺詳情。需真網路、不單測。"""
    from curl_cffi import requests as creq

    owns = session is None
    session = session or creq.Session(impersonate="chrome", timeout=30)
    try:
        if owns:
            session.get(_WARMUP_URL)  # 暖身，取 cookie
        resp = session.get(
            _DETAIL_URL.format(code=code),
            headers={"Referer": f"https://www.104.com.tw/job/{code}"},
        )
        resp.raise_for_status()
        return parse_job_detail(resp.json())
    finally:
        if owns:
            session.close()
