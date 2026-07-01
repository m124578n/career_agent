"""Spike：找出「個人化推薦職缺」真正的端點/來源頁，抓一筆 payload（SP5 用）。

用法（需先 `career-sentinel login` 過、關掉登入視窗）：
    uv run python spike/capture_recommend.py
"""

import json
from pathlib import Path

from rebrowser_playwright.sync_api import sync_playwright

from career_sentinel import browser

OUT = Path(__file__).resolve().parent / "captured"
OUT.mkdir(parents=True, exist_ok=True)

# 幾個可能觸發個人化推薦的登入頁
VISIT = [
    "https://www.104.com.tw/",
    "https://www.104.com.tw/jobs/main/",
    "https://www.104.com.tw/my/apply",
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
            if "recommend" in r.url.lower():
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    return
                (OUT / f"recommend__hit{saved}.json").write_text(
                    json.dumps({"url": r.url, "status": r.status,
                                "headers": dict(r.request.headers), "body": body},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8")
                saved += 1

        page.on("response", on_response)
        for url in VISIT:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                browser.wait_until_ready(page, timeout_ms=20000)
                # 捲動觸發 lazy-load 推薦區塊
                for _ in range(5):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(1200)
            except Exception as exc:  # noqa: BLE001
                print(f"[{url}] note: {type(exc).__name__}")
        page.remove_listener("response", on_response)

        # 保險：帶 Referer 直打
        for ref in ("https://www.104.com.tw/", "https://www.104.com.tw/jobs/main/"):
            try:
                resp = page.request.get(
                    "https://www.104.com.tw/api/jobs/personal-recommend-jobs?page=1&pageSize=20",
                    headers={"Referer": ref})
                print(f"direct(ref={ref}) status={resp.status}")
                if resp.ok:
                    (OUT / "recommend__direct.json").write_text(
                        json.dumps({"status": resp.status, "body": resp.json()}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                    saved += 1
                    break
            except Exception as exc:  # noqa: BLE001
                print(f"direct note: {type(exc).__name__}")
        ctx.close()

    (OUT / "recommend__allurls.txt").write_text("\n".join(all_urls), encoding="utf-8")
    print(f"攔到 {len(all_urls)} 個 API/JSON，存 {saved} 個 recommend payload。清單→ recommend__allurls.txt")


if __name__ == "__main__":
    main()
