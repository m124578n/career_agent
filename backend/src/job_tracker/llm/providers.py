"""各家 LLM provider 實作。新增 provider：寫一個 class，加進 _REGISTRY。"""

import json
import re
from typing import TypeVar

from pydantic import BaseModel

from job_tracker.config import get_settings
from job_tracker.llm.base import _DEFAULT_SYSTEM, LLMProvider

T = TypeVar("T", bound=BaseModel)


class OpenRouterProvider:
    """OpenRouter / 任何 OpenAI 相容端點。

    免費模型多半不支援嚴格 json_schema，故用 json_object 模式 +
    把 schema 塞進 system prompt，再以 Pydantic 驗證。
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            s = get_settings()
            self._client = AsyncOpenAI(
                api_key=s.openrouter_api_key, base_url=s.openrouter_base_url
            )
        return self._client

    async def complete(
        self, prompt: str, *, system: str = "", max_tokens: int = 2048, client=None
    ) -> str:
        client = client or self._get_client()
        resp = await client.chat.completions.create(
            model=get_settings().openrouter_model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system or _DEFAULT_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content or ""

    async def parse(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str = "",
        max_tokens: int = 4096,
        client=None,
    ) -> T:
        client = client or self._get_client()
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        full_system = (
            f"{system or _DEFAULT_SYSTEM}\n\n"
            "請只輸出符合以下 JSON Schema 的單一 JSON 物件，不要任何額外文字或說明：\n"
            f"{schema_json}"
        )
        resp = await client.chat.completions.create(
            model=get_settings().openrouter_model,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content or ""
        return schema.model_validate_json(_extract_json(content))


class AnthropicProvider:
    """Anthropic 原生：adaptive thinking + structured outputs（messages.parse）。"""

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    async def complete(
        self, prompt: str, *, system: str = "", max_tokens: int = 2048, client=None
    ) -> str:
        client = client or self._get_client()
        resp = await client.messages.create(
            model=get_settings().anthropic_model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system or _DEFAULT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")

    async def parse(
        self,
        prompt: str,
        schema: type[T],
        *,
        system: str = "",
        max_tokens: int = 4096,
        client=None,
    ) -> T:
        client = client or self._get_client()
        resp = await client.messages.parse(
            model=get_settings().anthropic_model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=system or _DEFAULT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        return resp.parsed_output


def _extract_json(text: str) -> str:
    """從模型輸出抽出 JSON：去掉 markdown 圍欄，取第一個 { 到最後一個 }。"""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


_REGISTRY: dict[str, type] = {
    "openrouter": OpenRouterProvider,
    "anthropic": AnthropicProvider,
}


def make_provider(name: str) -> LLMProvider:
    """依名稱建立 provider。未知名稱拋 ValueError。"""
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise ValueError(
            f"未知的 LLM provider：{name!r}（可用：{', '.join(_REGISTRY)}）"
        ) from None
