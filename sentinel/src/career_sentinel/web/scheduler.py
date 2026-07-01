from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..models import Settings


@dataclass
class _State:
    due: bool = False
    notify_time: str | None = None
    last_prompted_date: str | None = None
    started: bool = False


_state = _State()
_lock = threading.Lock()


def should_prompt(now: datetime, notify_time: str | None, last_prompted_date: str | None) -> bool:
    """到點（HH:MM >= notify_time）且今天尚未提醒 → True。notify_time None → False。"""
    if not notify_time:
        return False
    if last_prompted_date == now.date().isoformat():
        return False
    return now.strftime("%H:%M") >= notify_time


def initial_prompted_date(now: datetime, notify_time: str | None) -> str | None:
    """啟動當下若已過點（會立即觸發）→ 回今天（避免啟動即跳）；否則 None。"""
    if should_prompt(now, notify_time, None):
        return now.date().isoformat()
    return None


def _loop(load_settings: Callable[[], Settings]) -> None:
    while True:
        try:
            nt = load_settings().notify_time
            now = datetime.now()
            with _lock:
                _state.notify_time = nt
                if should_prompt(now, nt, _state.last_prompted_date):
                    _state.due = True
                    _state.last_prompted_date = now.date().isoformat()
        except Exception:  # noqa: BLE001 - 背景執行緒任何錯都不崩
            pass
        time.sleep(30)


def start(load_settings: Callable[[], Settings]) -> None:
    """起 daemon 背景執行緒（有 guard，多次呼叫只起一條）。啟動已過點不補觸發。"""
    with _lock:
        if _state.started:
            return
        _state.started = True
        try:
            now = datetime.now()
            nt = load_settings().notify_time
            _state.notify_time = nt
            _state.last_prompted_date = initial_prompted_date(now, nt)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_loop, args=(load_settings,), daemon=True).start()


def state() -> dict:
    with _lock:
        return {
            "due": _state.due,
            "notify_time": _state.notify_time,
            "last_prompted_date": _state.last_prompted_date,
        }


def ack() -> None:
    with _lock:
        _state.due = False


def _reset_for_test() -> None:
    with _lock:
        _state.due = False
        _state.notify_time = None
        _state.last_prompted_date = None
        _state.started = False
