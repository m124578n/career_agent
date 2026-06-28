from __future__ import annotations

from .. import browser
from ..models import Snapshot
from .applications import fetch_applications
from .messages import fetch_messages
from .viewers import fetch_viewers

ESTABLISH_URL = "https://pda.104.com.tw/"


def establish_session(page) -> bool:
    """navigate 一個 pda 頁（取得該 host 的 Cloudflare clearance）並確認已登入。

    需真瀏覽器、不單測。回 False 代表未登入（呼叫端應提示先 login）。
    """
    page.goto(ESTABLISH_URL, wait_until="domcontentloaded")
    browser.wait_until_ready(page)
    return not browser.is_login_url(page.url)


def scrape(page) -> tuple[Snapshot, set[str]]:
    """逐讀取器抓取；單一失敗只記進 failed、不中斷其他。"""
    readers = (
        ("viewers", fetch_viewers),
        ("applications", fetch_applications),
        ("messages", fetch_messages),
    )
    collected: dict[str, list] = {"viewers": [], "applications": [], "messages": []}
    failed: set[str] = set()
    for name, fn in readers:
        try:
            collected[name] = fn(page)
        except Exception:
            failed.add(name)
    snapshot = Snapshot(
        viewers=collected["viewers"],
        applications=collected["applications"],
        messages=collected["messages"],
    )
    return snapshot, failed
