from __future__ import annotations

from . import config

# 登入後才看得到的探針頁（spike 時校正成穩定的私人頁）
LOGGED_IN_PROBE_URL = "https://www.104.com.tw/my/apply"


def is_login_url(url: str) -> bool:
    return "/login" in url or "account.104.com.tw" in url


def open_context(p):
    """launch_persistent_context：用專用 profile 開真 Chrome。需先 `playwright install chromium`。"""
    config.profile_dir().mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(config.profile_dir()),
        headless=False,
        channel="chrome",
    )


def ensure_logged_in(page) -> bool:
    page.goto(LOGGED_IN_PROBE_URL, wait_until="domcontentloaded")
    return not is_login_url(page.url)
