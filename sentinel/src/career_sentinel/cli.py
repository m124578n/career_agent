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
    from playwright.sync_api import sync_playwright

    print("開啟 Chrome，請在視窗內登入 104（含驗證碼）。登入完成後關閉視窗即可。")
    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.104.com.tw/", wait_until="domcontentloaded")
        input("登入完成後按 Enter 關閉…")
        ctx.close()
    return 0


def _cmd_run() -> int:
    from playwright.sync_api import sync_playwright

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
    except (SystemExit, argparse.ArgumentError):
        return 2
    if args.cmd == "login":
        return _cmd_login()
    if args.cmd == "run":
        return _cmd_run()
    parser.print_help()
    return 2
