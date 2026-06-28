from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


class LoginRequired(Exception):
    """抓取時偵測到未登入。"""


@dataclass
class _State:
    running: bool = False
    last_run: str | None = None
    last_error: str | None = None
    last_failed_readers: list[str] = field(default_factory=list)


_state = _State()
_lock = threading.Lock()


def status() -> dict:
    return {
        "running": _state.running,
        "last_run": _state.last_run,
        "last_error": _state.last_error,
        "last_failed_readers": list(_state.last_failed_readers),
    }


def start_scrape(launch_scrape: Callable[[], set[str]]) -> bool:
    """已在跑回 False；否則起背景執行緒跑 launch_scrape、回 True。"""
    with _lock:
        if _state.running:
            return False
        _state.running = True
    threading.Thread(target=_run, args=(launch_scrape,), daemon=True).start()
    return True


def _run(launch_scrape: Callable[[], set[str]]) -> None:
    try:
        failed = launch_scrape()
        _state.last_error = None
        _state.last_failed_readers = sorted(failed or [])
        _state.last_run = datetime.now().isoformat(timespec="seconds")
    except LoginRequired:
        _state.last_error = "請先 career-sentinel login"
    except Exception as exc:  # noqa: BLE001 - 任何抓取失敗都記錄、不讓執行緒崩
        _state.last_error = str(exc)
    finally:
        _state.running = False


def default_scrape(db_path: str | None = None) -> set[str]:
    """真實抓取：scrape_session → run_pipeline 存。未登入 raise LoginRequired。需真瀏覽器。"""
    from .. import cli, config, store
    from ..scraper import real

    result = real.scrape_session()
    if result is None:
        raise LoginRequired()
    failed = result[1]
    conn = store.connect(db_path or config.db_path())
    try:
        cli.run_pipeline(lambda: result, conn, now=datetime.now().isoformat(timespec="seconds"))
    finally:
        conn.close()
    return failed
