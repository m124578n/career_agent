"""LLM token 用量擷取與記錄。

providers 呼叫 record()；sink 預設 no-op，app 啟動時才接上 Mongo，
所以單元測試不會碰 DB。即使沒有 sink，也會把用量寫進 log。
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

logger = logging.getLogger("job_tracker.usage")

Sink = Callable[[dict], Awaitable[None]]
_sink: Sink | None = None


def set_sink(fn: Sink | None) -> None:
    global _sink
    _sink = fn


def _get(raw, key: str):
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw.get(key)
    return getattr(raw, key, None)


def normalize(provider: str, model: str, kind: str, raw) -> dict | None:
    """把 OpenAI（prompt/completion）或 Anthropic（input/output）的 usage 正規化。"""
    if raw is None:
        return None
    inp = _get(raw, "input_tokens")
    out = _get(raw, "output_tokens")
    if inp is None:
        inp = _get(raw, "prompt_tokens") or 0
    if out is None:
        out = _get(raw, "completion_tokens") or 0
    total = _get(raw, "total_tokens")
    if total is None:
        total = (inp or 0) + (out or 0)
    return {
        "ts": datetime.now(UTC),
        "provider": provider,
        "model": model,
        "kind": kind,
        "input_tokens": inp or 0,
        "output_tokens": out or 0,
        "total_tokens": total,
    }


async def record(provider: str, model: str, kind: str, raw) -> None:
    """記錄一次呼叫的用量（log + 寫入 sink）。usage 寫入失敗不影響主流程。"""
    rec = normalize(provider, model, kind, raw)
    if rec is None:
        return
    logger.info(
        "tokens %s/%s %s in=%d out=%d total=%d",
        provider,
        model,
        kind,
        rec["input_tokens"],
        rec["output_tokens"],
        rec["total_tokens"],
    )
    if _sink is not None:
        try:
            await _sink(rec)
        except Exception:
            logger.warning("token usage 寫入失敗", exc_info=True)
