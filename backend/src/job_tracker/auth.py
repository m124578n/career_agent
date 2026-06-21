"""Google OAuth 認證。驗證前端送來的 Google ID token，回傳使用者 email。

`google_client_id` 未設定時停用驗證（本機/測試），回傳 dev@local。
"""

import logging

from fastapi import Header, HTTPException

from job_tracker import context
from job_tracker.config import get_settings

logger = logging.getLogger("job_tracker.auth")


def is_admin(user: str) -> bool:
    """是否可看全站用量。停用驗證（本機）時一律視為 admin。"""
    s = get_settings()
    if not s.google_client_id:
        return True
    return user.lower() in s.admin_email_list


def _default_verify(token: str, client_id: str) -> dict:
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, g_requests.Request(), client_id)


_verifier = _default_verify


def set_verifier(fn) -> None:
    """測試用：替換 token 驗證實作。"""
    global _verifier
    _verifier = fn


async def current_user(authorization: str | None = Header(default=None)) -> str:
    """FastAPI 依賴：回傳已驗證的使用者 email。未登入/無效 → 401。"""
    settings = get_settings()
    if not settings.google_client_id:
        context.current_user.set("dev@local")
        return "dev@local"  # 驗證停用（本機開發/測試）

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="需要登入")
    token = authorization[len("Bearer ") :]
    try:
        claims = _verifier(token, settings.google_client_id)
        email = claims.get("email")
    except Exception as e:
        logger.warning("Google token verify failed: %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=401, detail="登入無效") from None
    if not email:
        raise HTTPException(status_code=401, detail="登入缺少 email")
    context.current_user.set(email)  # 供 LLM 用量歸戶
    return email
