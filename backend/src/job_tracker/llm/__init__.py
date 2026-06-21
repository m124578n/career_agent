"""LLM 抽象層。對外只暴露 complete() / parse()，底層 provider 可抽換。

換 provider 只改 config 的 `llm_provider`（openrouter / anthropic）；
新增 provider 改 providers.py 的 _REGISTRY。下游服務完全不用動。
"""

from typing import TypeVar

from pydantic import BaseModel

from job_tracker.config import get_settings
from job_tracker.llm.base import LLMProvider
from job_tracker.llm.providers import make_provider

T = TypeVar("T", bound=BaseModel)

_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """取得目前設定的 provider（依 config.llm_provider，單例快取）。"""
    global _provider
    if _provider is None:
        _provider = make_provider(get_settings().llm_provider)
    return _provider


async def complete(
    prompt: str, *, system: str = "", max_tokens: int = 2048, client=None
) -> str:
    return await get_provider().complete(
        prompt, system=system, max_tokens=max_tokens, client=client
    )


async def parse(
    prompt: str,
    schema: type[T],
    *,
    system: str = "",
    max_tokens: int = 4096,
    client=None,
) -> T:
    return await get_provider().parse(
        prompt, schema, system=system, max_tokens=max_tokens, client=client
    )
