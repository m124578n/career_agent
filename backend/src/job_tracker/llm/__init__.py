"""LLM client 抽象層。MVP 用 Claude（Anthropic），之後可換/併 OpenAI。"""

from anthropic import AsyncAnthropic

from job_tracker.config import get_settings

_client: AsyncAnthropic | None = None


def get_llm() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


async def complete(prompt: str, *, system: str = "", max_tokens: int = 2048) -> str:
    """送一段 prompt，回傳純文字。各 service 的共用入口。"""
    resp = await get_llm().messages.create(
        model=get_settings().llm_model,
        max_tokens=max_tokens,
        system=system or "你是一位專業的求職顧問。",
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")
