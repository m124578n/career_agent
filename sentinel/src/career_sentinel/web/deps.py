"""共用相依：從 app.state 取得資料庫路徑供各 router 使用。"""
from __future__ import annotations

from fastapi import Request


def get_db_path(request: Request) -> str:
    return request.app.state.db_path
