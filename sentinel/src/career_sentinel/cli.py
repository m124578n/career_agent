from __future__ import annotations

import argparse
from datetime import datetime
from typing import Callable

from . import browser, config, diff, digest, store
from .models import Snapshot
from .scraper import fake


def run_pipeline(scrape: Callable[[], tuple[Snapshot, set[str]]], conn, *, now: str) -> str:
    snapshot, failed = scrape()
    if failed:
        snapshot = _carry_forward(conn, snapshot, failed)
    sid = store.save_snapshot(conn, snapshot, run_at=now)
    d = diff.diff_against_last(conn, sid)
    report = digest.summarize(d, snapshot)
    if failed:
        report += "\n\n⚠️ 本次未讀到：" + "、".join(sorted(failed)) + "（沿用上次）"
    return report


def _carry_forward(conn, snapshot: Snapshot, failed: set[str]) -> Snapshot:
    """失敗的讀取器沿用上次快照同類資料，避免下次 diff 把整類誤判為新。"""
    ids = store.latest_two_ids(conn)
    if not ids:
        return snapshot
    prev = store.load_snapshot(conn, ids[0])
    return Snapshot(
        viewers=prev.viewers if "viewers" in failed else snapshot.viewers,
        applications=prev.applications if "applications" in failed else snapshot.applications,
        messages=prev.messages if "messages" in failed else snapshot.messages,
    )


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
    from .scraper import real

    conn = store.connect(config.db_path())
    result = real.scrape_session()
    if result is None:
        print("尚未登入，請先執行：career-sentinel login")
        return 1
    report = run_pipeline(
        lambda: result,
        conn,
        now=datetime.now().isoformat(timespec="seconds"),
    )
    print(report)
    return 0


def _cmd_serve() -> int:
    import threading
    import webbrowser

    import uvicorn

    from .web.app import create_app

    url = "http://127.0.0.1:8765"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"career-sentinel 儀表板：{url}（Ctrl+C 結束）")
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="career-sentinel", exit_on_error=False)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("login", help="首次：開 Chrome 手動登入 104")
    sub.add_parser("run", help="擷取 → 比對 → 彙整")
    sub.add_parser("serve", help="起本地 web 儀表板")
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError:
        return 2
    if args.cmd == "login":
        return _cmd_login()
    if args.cmd == "run":
        return _cmd_run()
    if args.cmd == "serve":
        return _cmd_serve()
    parser.print_help()
    return 2
