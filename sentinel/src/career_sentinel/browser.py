from __future__ import annotations

from . import config

# 登入後才看得到的探針頁（spike 時校正成穩定的私人頁）
LOGGED_IN_PROBE_URL = "https://www.104.com.tw/my/apply"


def is_login_url(url: str) -> bool:
    return "/login" in url or "account.104.com.tw" in url


# 注入到每個頁面最早期，遮掉 Playwright/CDP 殘留的自動化特徵。
# `--disable-blink-features=AutomationControlled` 已讓 navigator.webdriver=undefined，
# 這段是雙保險，並順手補上常被反爬 SDK 探測的 webdriver 屬性。
_STEALTH_INIT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


def open_context(p):
    """launch_persistent_context：用專用 profile 開真 Chrome（去自動化特徵）。

    需先 `playwright install chromium`。三招去特徵：
    - `--disable-blink-features=AutomationControlled`：移除 navigator.webdriver 旗標
    - `ignore_default_args=["--enable-automation"]`：拿掉「Chrome 受自動化控制」資訊列與旗標
    - `add_init_script`：頁面載入最早期再遮一次 webdriver（雙保險）
    """
    profile = config.profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    ctx.add_init_script(_STEALTH_INIT)
    return ctx


def ensure_logged_in(page) -> bool:
    page.goto(LOGGED_IN_PROBE_URL, wait_until="domcontentloaded")
    return not is_login_url(page.url)
