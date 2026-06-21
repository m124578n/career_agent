"""請求層的當前使用者（contextvar）。

auth 在驗證後寫入；解耦的 LLM 記錄層讀取，藉此把 token 用量歸到使用者，
而不必把 user 一路傳進 LLM 介面。
"""

import contextvars

current_user: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user", default="unknown"
)
