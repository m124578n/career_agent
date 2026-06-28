"""Spike：帶登入 profile 自動造訪 104 三類頁面，攔截 JSON 回應存檔。

用法（需先 `career-sentinel login` 過、且關掉那個登入視窗）：
    uv run python spike/capture_104.py

輸出到 spike/captured/<name>__<i>.json（含 url/status/body）。**含個資，已 gitignore，勿提交。**
拿來確認端點與結構；正式 fixture 請去識別化後放 tests/fixtures/。
詳見 spike/FINDINGS.md。
"""

import json
from pathlib import Path

from rebrowser_playwright.sync_api import sync_playwright

from career_sentinel import browser, config

OUT = Path(__file__).resolve().parent / "captured"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = {
    "viewers": "https://pda.104.com.tw/work/peruseRecord",        # 誰看過我
    "messages": "https://pda.104.com.tw/work/message/chat",       # 訊息／面試邀約
    "applications": "https://pda.104.com.tw/applyRecord/",        # 我的應徵
}

# 排除分析/第三方/靜態噪音，只留可能帶資料的 JSON
NOISE = (
    "cloudflare", "google", "facebook", "hotjar", "ipify",
    "static.104", "/log/", "analytics", "gtag", "gstatic", "doubleclick",
)


def _interesting(r) -> bool:
    url = r.url
    if any(n in url for n in NOISE):
        return False
    ctype = r.headers.get("content-type", "")
    return "application/json" in ctype or "/api/" in url or "/ajax/" in url


def main() -> None:
    with sync_playwright() as p:
        ctx = browser.open_context(p)  # headful（headless 過不了 Cloudflare）
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for name, url in PAGES.items():
            hits: list = []

            def on_response(r, _hits=hits):
                if _interesting(r):
                    _hits.append(r)

            page.on("response", on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                browser.wait_until_ready(page, timeout_ms=25000)
                page.wait_for_timeout(6000)
            except Exception as exc:  # noqa: BLE001 - spike 探查，容忍
                print(f"[{name}] goto note: {type(exc).__name__}")
            page.remove_listener("response", on_response)

            saved = 0
            for i, r in enumerate(hits):
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    continue
                (OUT / f"{name}__{i}.json").write_text(
                    json.dumps({"url": r.url, "status": r.status, "body": body}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                saved += 1
            print(f"[{name}] final_url={page.url} 存 {saved} 個 JSON")
        ctx.close()
    print("輸出目錄:", OUT)


if __name__ == "__main__":
    main()
