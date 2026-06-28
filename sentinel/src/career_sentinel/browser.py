from __future__ import annotations

import os

from . import config

# rebrowser-patches 的 Runtime.enable 修補模式（過 Cloudflare 的關鍵）。
# 在啟動瀏覽器前設好即可；使用者可用環境變數覆寫切換 addBinding/alwaysIsolated/0。
os.environ.setdefault("REBROWSER_PATCHES_RUNTIME_FIX_MODE", "addBinding")

# 登入後才看得到的探針頁（spike 時校正成穩定的私人頁）
LOGGED_IN_PROBE_URL = "https://www.104.com.tw/my/apply"


def is_login_url(url: str) -> bool:
    return "/login" in url or "account.104.com.tw" in url


def find_chrome() -> str | None:
    """找系統 Google Chrome 執行檔（供『純 Chrome 登入』用，完全不經 Playwright/CDP）。

    手動登入需要正常可操作的瀏覽器；經 rebrowser 的 patch 會卡住人手動導覽，
    故登入改開純 Chrome。優先讀登錄檔 App Paths，再退回常見安裝路徑。
    """
    candidates: list[str] = []
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        ) as key:
            val, _ = winreg.QueryValueEx(key, None)
            if val:
                candidates.append(val)
    except OSError:
        pass
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


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


def wait_until_ready(page, timeout_ms: int = 20000) -> bool:
    """等 Cloudflare『Just a moment / 驗證中』介面自行通過。

    rebrowser-patches 下多半 ~10s 內會自動過關、跳回真實頁面。
    回傳 True=已就緒、False=逾時仍卡在 challenge。spike 實機驗證、不單測。
    """
    import time

    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""
        if title and "moment" not in title and "verifying" not in title:
            return True
        page.wait_for_timeout(1000)
    return False


def ensure_logged_in(page) -> bool:
    page.goto(LOGGED_IN_PROBE_URL, wait_until="domcontentloaded")
    wait_until_ready(page)
    return not is_login_url(page.url)
