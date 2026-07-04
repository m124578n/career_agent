"""SP13：LLM token 用量與花費記錄。best-effort，絕不影響 LLM 呼叫。"""
from __future__ import annotations

from datetime import datetime

from . import config, store

# $/M tokens。預設套 Claude Sonnet 4.5 官方單價（Foundry 實際計費可能不同、此表可調）。
_PRICING: dict[str, dict[str, float]] = {
    "sonnet": {"in": 3.00, "out": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "default": {"in": 3.00, "out": 15.00, "cache_read": 0.30, "cache_write": 3.75},
}


def _price_for(model: str) -> dict[str, float]:
    m = (model or "").lower()
    for key, price in _PRICING.items():
        if key != "default" and key in m:
            return price
    return _PRICING["default"]


def cost_of(model: str, input_tokens: int, output_tokens: int,
            cache_read: int, cache_write: int) -> float:
    p = _price_for(model)
    return (
        input_tokens * p["in"]
        + output_tokens * p["out"]
        + cache_read * p["cache_read"]
        + cache_write * p["cache_write"]
    ) / 1_000_000


def _get(raw, name):
    if isinstance(raw, dict):
        return raw.get(name)
    return getattr(raw, name, None)


def normalize(raw) -> dict:
    """兩家 provider 的 usage 正規化成 input/output/cache_read/cache_write（int）。"""
    if raw is None:
        return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    a_in = _get(raw, "input_tokens")
    if a_in is not None:  # Anthropic：input_tokens 不含 cache
        return {
            "input": int(a_in or 0),
            "output": int(_get(raw, "output_tokens") or 0),
            "cache_read": int(_get(raw, "cache_read_input_tokens") or 0),
            "cache_write": int(_get(raw, "cache_creation_input_tokens") or 0),
        }
    prompt = _get(raw, "prompt_tokens")
    if prompt is not None:  # OpenAI：prompt_tokens 含 cache
        details = _get(raw, "prompt_tokens_details")
        if isinstance(details, dict):
            cached = details.get("cached_tokens") or 0
        else:
            cached = getattr(details, "cached_tokens", 0) or 0
        cached = int(cached)
        return {
            "input": max(int(prompt) - cached, 0),
            "output": int(_get(raw, "completion_tokens") or 0),
            "cache_read": cached,
            "cache_write": 0,
        }
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def record(feature: str, model: str, raw, *, db=None) -> None:
    """記一列 usage_log。best-effort：任何例外都吞掉，絕不影響 LLM 呼叫。"""
    try:
        n = normalize(raw)
        cost = cost_of(model, n["input"], n["output"], n["cache_read"], n["cache_write"])
        conn = store.connect(db or config.db_path())
        try:
            conn.execute(
                "INSERT INTO usage_log "
                "(feature, model, input_tokens, output_tokens, cache_read, cache_write, cost_usd, at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (feature, model or "", n["input"], n["output"], n["cache_read"],
                 n["cache_write"], cost, datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — 記帳絕不影響主流程
        pass


def summary(conn) -> dict:
    total_tokens = conn.execute(
        "SELECT COALESCE(SUM(input_tokens+output_tokens+cache_read+cache_write),0) FROM usage_log"
    ).fetchone()[0]
    total_usd = conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM usage_log").fetchone()[0]
    rows = conn.execute(
        "SELECT feature, COUNT(*), "
        "COALESCE(SUM(input_tokens+output_tokens+cache_read+cache_write),0), "
        "COALESCE(SUM(cost_usd),0) "
        "FROM usage_log GROUP BY feature ORDER BY SUM(cost_usd) DESC"
    ).fetchall()
    by_feature = [
        {"feature": r[0], "calls": int(r[1]), "tokens": int(r[2]), "usd": float(r[3])}
        for r in rows
    ]
    return {"total_tokens": int(total_tokens), "total_usd": float(total_usd), "by_feature": by_feature}


def reset(conn) -> None:
    conn.execute("DELETE FROM usage_log")
    conn.commit()
