from __future__ import annotations

from urllib.parse import quote

from ..models import RecommendedJob
from .recommend import parse_recommendations

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs?keyword={kw}&page=1&pagesize=20&order=15&asc=0&mode=s"
_WARMUP_URL = "https://www.104.com.tw/jobs/search/"


def parse_search(payload: dict) -> list[RecommendedJob]:
    """搜尋結果職缺結構與推薦完全相同，委派 parse_recommendations。"""
    return parse_recommendations(payload)


def fetch_search(keyword: str, *, session=None) -> list[RecommendedJob]:
    """curl_cffi 打 104 公開職缺搜尋 API。公開資料、不需登入。需真網路、不單測。"""
    from curl_cffi import requests as creq

    owns = session is None
    session = session or creq.Session(impersonate="chrome", timeout=30)
    try:
        kw = quote(keyword)
        if owns:
            session.get(_WARMUP_URL)  # 暖身取 cookie
        resp = session.get(
            SEARCH_URL.format(kw=kw),
            headers={"Referer": f"https://www.104.com.tw/jobs/search/?keyword={kw}"},
        )
        resp.raise_for_status()
        return parse_search(resp.json())
    finally:
        if owns:
            session.close()
