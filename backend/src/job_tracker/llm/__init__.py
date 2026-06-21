"""LLM client 抽象層。MVP 用 Claude（Anthropic），預設 claude-opus-4-8 + adaptive thinking。"""

from typing import TypeVar

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from job_tracker.config import get_settings

_client: AsyncAnthropic | None = None

T = TypeVar("T", bound=BaseModel)


def get_llm() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


async def complete(prompt: str, *, system: str = "", max_tokens: int = 2048) -> str:
    """送一段 prompt，回傳純文字（自由文字產生，如求職信）。"""
    resp = await get_llm().messages.create(
        model=get_settings().llm_model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system or "你是一位專業的求職顧問。",
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


async def parse(
    prompt: str,
    schema: type[T],
    *,
    system: str = "",
    max_tokens: int = 4096,
    client: AsyncAnthropic | None = None,
) -> T:
    """送一段 prompt，回傳依 `schema` 驗證的結構化輸出（structured outputs）。"""
    client = client or get_llm()
    resp = await client.messages.parse(
        model=get_settings().llm_model,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        system=system or "你是一位專業的求職顧問。",
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    return resp.parsed_output
