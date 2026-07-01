"""Spike：找 104 面試場次的端點與結構（SP7 用）。

用法（需先 career-sentinel login 過、關掉登入視窗）：
    uv run python spike/capture_interviews.py
攔訊息/面試頁所有 API/JSON + 直打候選面試端點。輸出 spike/captured/interview__*.json（已 gitignore）。
"""

import json
from pathlib import Path

from rebrowser_playwright.sync_api import sync_playwright

from career_sentinel import browser

OUT = Path(__file__).resolve().parent / "captured"
OUT.mkdir(parents=True, exist_ok=True)

# 面試相關頁（登入後）
VISIT = [
    "https://pda.104.com.tw/work/message/chat",
    "https://pda.104.com.tw/work/message/interview",
]
# 直打候選端點（FINDINGS 線索 + 猜測）
DIRECT = [
    "https://pda.104.com.tw/work/message/ajax/options",
    "https://pda.104.com.tw/api/messages/interviews?page=1&pageSize=20",
    "https://pda.104.com.tw/api/interviews?page=1&pageSize=20",
]
NOISE = ("cloudflare", "google", "facebook", "hotjar", "ipify", "static.104",
         "/log/", "analytics", "gtag", "gstatic", "doubleclick", ".png", ".jpg", ".css", ".js", ".woff")


def _interesting(url: str, ctype: str) -> bool:
    if any(n in url for n in NOISE):
        return False
    return "application/json" in ctype or "/api/" in url or "/ajax/" in url


def main() -> None:
    all_urls: list[str] = []
    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        saved = 0

        def on_response(r):
            nonlocal saved
            ctype = r.headers.get("content-type", "")
            if not _interesting(r.url, ctype):
                return
            all_urls.append(f"{r.status} {r.url}")
            low = r.url.lower()
            if "interview" in low or "options" in low:
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    return
                (OUT / f"interview__xhr{saved}.json").write_text(
                    json.dumps({"url": r.url, "status": r.status, "body": body}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                saved += 1

        page.on("response", on_response)
        for url in VISIT:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                browser.wait_until_ready(page, timeout_ms=20000)
                page.wait_for_timeout(5000)
            except Exception as exc:  # noqa: BLE001
                print(f"[{url}] note: {type(exc).__name__}")
        page.remove_listener("response", on_response)
        print(f"final_url={page.url} login={browser.is_login_url(page.url)}")

        for url in DIRECT:
            try:
                r = page.request.get(url)
                print(f"direct {url} -> {r.status}")
                if r.ok:
                    try:
                        body = r.json()
                    except Exception:  # noqa: BLE001
                        continue
                    name = url.rsplit("/", 1)[-1].split("?")[0]
                    (OUT / f"interview__direct_{name}.json").write_text(
                        json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")
                    saved += 1
            except Exception as exc:  # noqa: BLE001
                print(f"direct {url} note: {type(exc).__name__}")
        ctx.close()

    (OUT / "interview__allurls.txt").write_text("\n".join(all_urls), encoding="utf-8")
    print(f"攔到 {len(all_urls)} 個 API/JSON，存 {saved} 個 interview payload。清單→ interview__allurls.txt")


if __name__ == "__main__":
    main()
