from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode

from .models import Interview

_RENDER = "https://calendar.google.com/calendar/render"
_IN_FMT = "%Y-%m-%d %H:%M:%S"
_OUT_FMT = "%Y%m%dT%H%M%S"


def _to_dates(when: str) -> str | None:
    """'2026-04-07 10:00:00' → '20260407T100000/20260407T110000'（起/起+1h）；不可解析回 None。"""
    try:
        start = datetime.strptime(when, _IN_FMT)
    except (ValueError, TypeError):
        return None
    end = start + timedelta(hours=1)
    return f"{start.strftime(_OUT_FMT)}/{end.strftime(_OUT_FMT)}"


def build_gcal_link(iv: Interview) -> str:
    """產生 Google Calendar 預填新增事件連結（零 OAuth）。無/不可解析時間 → 不帶 dates。"""
    details = f"職缺：{iv.job_title}"
    if iv.job_url:
        details += f"\n{iv.job_url}"
    params = {
        "action": "TEMPLATE",
        "text": f"面試：{iv.company}",
        "details": details,
    }
    if iv.location:
        params["location"] = iv.location
    dates = _to_dates(iv.when)
    if dates:
        params["dates"] = dates
    return f"{_RENDER}?{urlencode(params)}"
