"""Spike：找 104 登入態「讀取現有履歷」的端點與結構（SP12 用）。

用法（需先 career-sentinel login 過、關掉登入視窗）：
    uv run python spike/capture_resume.py

造訪 104 履歷管理區、攔所有 API/JSON 回應 + 直打候選履歷端點。
輸出 spike/captured/resume__*.json（已 gitignore）。

目標：查清 104 有沒有登入態端點回傳目前履歷（結構化分欄 or 自由文字），
決定 SP12 能否做真正的 diff 比對。
"""

import json
from pathlib import Path

from rebrowser_playwright.sync_api import sync_playwright

from career_sentinel import browser

OUT = Path(__file__).resolve().parent / "captured"
OUT.mkdir(parents=True, exist_ok=True)

# 履歷管理相關頁（登入後）——涵蓋常見 104 履歷入口，讓 XHR 自己冒出來
VISIT = [
    "https://pda.104.com.tw/my/resume",
    "https://pda.104.com.tw/resume",
    "https://pda.104.com.tw/my104/myCenter",
    "https://pda.104.com.tw/my/resume/list",
]
# 直打候選端點（依既有 pda api 命名慣例猜；攔到線索後可再補跑）
DIRECT = [
    "https://pda.104.com.tw/api/resumes?page=1&pageSize=20",
    "https://pda.104.com.tw/api/resumes",
    "https://pda.104.com.tw/api/resume",
    "https://pda.104.com.tw/api/resume/list",
    "https://pda.104.com.tw/api/my/resumes",
]
NOISE = ("cloudflare", "google", "facebook", "hotjar", "ipify", "static.104",
         "/log/", "analytics", "gtag", "gstatic", "doubleclick", ".png", ".jpg", ".css", ".js", ".woff")
# 履歷相關關鍵字（url 命中才存 payload，避免存一堆無關 JSON）
RESUME_HINT = ("resume", "履歷", "profile", "autobiography", "experience", "education", "cv")


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
            if any(h in low for h in RESUME_HINT):
                try:
                    body = r.json()
                except Exception:  # noqa: BLE001
                    return
                (OUT / f"resume__xhr{saved}.json").write_text(
                    json.dumps({"url": r.url, "status": r.status, "body": body}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                saved += 1

        page.on("response", on_response)
        for url in VISIT:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                browser.wait_until_ready(page, timeout_ms=20000)
                page.wait_for_timeout(5000)
                print(f"visited {url} -> {page.url}")
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
                    name = url.rsplit("/", 1)[-1].split("?")[0] or "root"
                    (OUT / f"resume__direct_{name}.json").write_text(
                        json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2), encoding="utf-8")
                    saved += 1
            except Exception as exc:  # noqa: BLE001
                print(f"direct {url} note: {type(exc).__name__}")
        ctx.close()

    (OUT / "resume__allurls.txt").write_text("\n".join(all_urls), encoding="utf-8")
    print(f"攔到 {len(all_urls)} 個 API/JSON，存 {saved} 個 resume payload。清單→ captured/resume__allurls.txt")
    print("下一步：看 captured/resume__*.json 有無結構化履歷欄位（工作經歷/學歷/專長/自傳），回報給我。")


if __name__ == "__main__":
    main()
