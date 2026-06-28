from __future__ import annotations

import argparse
from datetime import datetime
from typing import Callable

from . import browser, config, diff, digest, store
from .models import Snapshot
from .scraper import fake


def run_pipeline(scrape: Callable[[], Snapshot], conn, *, now: str) -> str:
    snapshot = scrape()
    sid = store.save_snapshot(conn, snapshot, run_at=now)
    d = diff.diff_against_last(conn, sid)
    return digest.summarize(d, snapshot)


def _cmd_login() -> int:
    # 登入要人手動操作，故開「純 Chrome」（不經 Playwright/CDP）——rebrowser 的 patch
    # 會卡住人手動導覽。登入態存進專用 profile，之後 run 再用 rebrowser 自動讀。
    import subprocess

    chrome = browser.find_chrome()
    if not chrome:
        print("找不到 Google Chrome，請確認已安裝。")
        return 1
    profile = config.profile_dir()
    profile.mkdir(parents=True, exist_ok=True)
    print("開啟純 Chrome（無自動化）登入 104——像平常一樣過 Cloudflare、輸入帳密。")
    print("登入成功後，回這裡按 Enter，再關閉那個 Chrome 視窗即可。")
    subprocess.Popen(
        [
            chrome,
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://www.104.com.tw/",
        ]
    )
    input("登入完成後按 Enter…")
    return 0


def _cmd_run() -> int:
    from rebrowser_playwright.sync_api import sync_playwright

    conn = store.connect(config.db_path())
    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not browser.ensure_logged_in(page):
            ctx.close()
            print("尚未登入，請先執行：career-sentinel login")
            return 1
        ctx.close()
    # Phase 1：先用假爬蟲；Phase 2 改成真爬蟲 scraper.scrape(page)
    # Phase 2: real scraper needs the page — move this pipeline call INSIDE the `with sync_playwright()` block, before ctx.close().
    report = run_pipeline(fake.scrape, conn, now=datetime.now().isoformat(timespec="seconds"))
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="career-sentinel", exit_on_error=False)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("login", help="首次：開 Chrome 手動登入 104")
    sub.add_parser("run", help="擷取 → 比對 → 彙整")
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError:
        return 2
    if args.cmd == "login":
        return _cmd_login()
    if args.cmd == "run":
        return _cmd_run()
    parser.print_help()
    return 2
