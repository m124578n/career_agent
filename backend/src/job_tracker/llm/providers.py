"""各家 LLM provider 實作。新增 provider：寫一個 class，加進 _REGISTRY。"""

import json
import logging
import re
import time
from typing import TypeVar

from pydantic import BaseModel

from job_tracker.config import get_settings
from job_tracker.llm.base import _DEFAULT_SYSTEM, LLMProvider

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger("job_tracker.llm")


def _log_call(kind: str, model: str, start: float, error: Exception | None = None):
    dur = time.perf_counter() - start
    if error is None:
        logger.info("llm.%s model=%s %.2fs ok", kind, model, dur)
    else:
        logger.warning(
            "llm.%s model=%s %.2fs FAILED %s", kind, model, dur, type(error).__name__
        )


class _OpenAICompatProvider:
    """OpenAI 相容端點的共用邏輯（OpenRouter / Azure 都吃這套）。

    免費/多數模型不一定支援嚴格 json_schema，故用 json_object 模式 +
    把 schema 塞進 system prompt，再以 Pydantic 驗證（含去 markdown 圍欄）。
    子類別只需實作 _make_client() 與 _model()。
    """

    def __init__(self):
        self._client = None

    def _make_client(self):
        raise NotImplementedError

    def _model(self) -> str:
        raise NotImplementedError

    def _get_client(self):
        if self._client is None:
            self._client = self._make_client()
        return self._client

    async def complete(
        self, prompt: str, *, system: str = "", max_tokens: int = 2048, client=None
    ) -> str:
        client = client or self._get_client()
        model = self._model()
        start = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system or _DEFAULT_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )
            _log_call("complete", model, start)
            return resp.choices[0].message.content or ""
        except Exception as e:
            _log_call("complete", model, start, e)
            raise

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
        model = self._model()
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        full_system = (
            f"{system or _DEFAULT_SYSTEM}\n\n"
            "請只輸出符合以下 JSON Schema 的單一 JSON 物件，不要任何額外文字或說明：\n"
            f"{schema_json}"
        )
        start = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": prompt},
                ],
            )
            content = resp.choices[0].message.content or ""
            result = schema.model_validate_json(_extract_json(content))
            _log_call("parse", model, start)
            return result
        except Exception as e:
            _log_call("parse", model, start, e)
            raise


class OpenRouterProvider(_OpenAICompatProvider):
    """OpenRouter / 任何 OpenAI 相容端點。"""

    def _make_client(self):
        from openai import AsyncOpenAI

        s = get_settings()
        return AsyncOpenAI(api_key=s.openrouter_api_key, base_url=s.openrouter_base_url)

    def _model(self) -> str:
        return get_settings().openrouter_model


class AzureProvider(_OpenAICompatProvider):
    """Azure OpenAI。model 用 Azure 上的 deployment 名稱。"""

    def _make_client(self):
        from openai import AsyncAzureOpenAI

        s = get_settings()
        return AsyncAzureOpenAI(
            api_key=s.azure_openai_api_key,
            api_version=s.azure_openai_api_version,
            azure_endpoint=s.azure_openai_endpoint,
        )

    def _model(self) -> str:
        return get_settings().azure_openai_deployment


class _AnthropicBaseProvider:
    """Anthropic 原生 Messages API 的共用邏輯（直連 Anthropic / Azure Foundry 共用）。

    adaptive thinking + structured outputs（messages.parse）。
    子類別只需實作 _make_client() 與 _model()。
    """

    def __init__(self):
        self._client = None

    def _make_client(self):
        raise NotImplementedError

    def _model(self) -> str:
        raise NotImplementedError

    def _get_client(self):
        if self._client is None:
            self._client = self._make_client()
        return self._client

    async def complete(
        self, prompt: str, *, system: str = "", max_tokens: int = 2048, client=None
    ) -> str:
        client = client or self._get_client()
        model = self._model()
        start = time.perf_counter()
        try:
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                system=system or _DEFAULT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            _log_call("complete", model, start)
            return "".join(b.text for b in resp.content if b.type == "text")
        except Exception as e:
            _log_call("complete", model, start, e)
            raise

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
        model = self._model()
        start = time.perf_counter()
        try:
            resp = await client.messages.parse(
                model=model,
                max_tokens=max_tokens,
                thinking={"type": "adaptive"},
                system=system or _DEFAULT_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
            )
            _log_call("parse", model, start)
            return resp.parsed_output
        except Exception as e:
            _log_call("parse", model, start, e)
            raise


class AnthropicProvider(_AnthropicBaseProvider):
    """直連 Anthropic。"""

    def _make_client(self):
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=get_settings().anthropic_api_key)

    def _model(self) -> str:
        return get_settings().anthropic_model


class FoundryProvider(_AnthropicBaseProvider):
    """Azure AI Foundry 上的 Claude（原生 Anthropic API，端點 .../anthropic）。"""

    def _make_client(self):
        from anthropic import AsyncAnthropicFoundry

        s = get_settings()
        return AsyncAnthropicFoundry(
            api_key=s.foundry_api_key, base_url=s.foundry_base_url
        )

    def _model(self) -> str:
        return get_settings().foundry_model


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
    "azure": AzureProvider,
    "foundry": FoundryProvider,
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
