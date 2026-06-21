"""llm provider 抽象 + OpenRouter / Anthropic 各自的結構化輸出邏輯。"""

import pytest

from job_tracker import llm
from job_tracker.config import get_settings
from job_tracker.llm import make_provider
from job_tracker.llm.providers import (
    AnthropicProvider,
    AzureProvider,
    FoundryProvider,
    OpenRouterProvider,
)
from job_tracker.schemas import MatchAnalysis


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        message = type("Msg", (), {"content": self._content})()
        choice = type("Choice", (), {"message": message})()
        return type("Resp", (), {"choices": [choice]})()


class _FakeClient:
    def __init__(self, content: str):
        self.chat = type("Chat", (), {"completions": _FakeCompletions(content)})()


async def test_parse_validates_json_into_schema():
    client = _FakeClient('{"score": 80, "reasons": ["技能符合"], "gaps": ["缺經驗"]}')
    result = await llm.parse("prompt", MatchAnalysis, client=client)
    assert isinstance(result, MatchAnalysis)
    assert result.score == 80
    assert result.reasons == ["技能符合"]


async def test_parse_strips_markdown_fences():
    # 免費模型常把 JSON 包在 ```json ... ``` 裡
    client = _FakeClient('```json\n{"score": 60, "reasons": [], "gaps": []}\n```')
    result = await llm.parse("prompt", MatchAnalysis, client=client)
    assert result.score == 60


async def test_parse_requests_json_response_format():
    client = _FakeClient('{"score": 1, "reasons": [], "gaps": []}')
    await llm.parse("prompt", MatchAnalysis, client=client)
    sent = client.chat.completions.calls[0]
    assert sent["response_format"] == {"type": "json_object"}


# --- provider 抽象 ---


def test_make_provider_selects_by_name():
    assert isinstance(make_provider("openrouter"), OpenRouterProvider)
    assert isinstance(make_provider("anthropic"), AnthropicProvider)
    assert isinstance(make_provider("azure"), AzureProvider)


async def test_azure_provider_parse_uses_deployment_and_json():
    client = _FakeClient('{"score": 55, "reasons": [], "gaps": []}')
    result = await AzureProvider().parse("prompt", MatchAnalysis, client=client)
    assert result.score == 55
    sent = client.chat.completions.calls[0]
    # Azure 與 OpenRouter 共用 OpenAI 相容邏輯：json_object + deployment 當 model
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["model"] == get_settings().azure_openai_deployment


def test_make_provider_unknown_raises():
    with pytest.raises(ValueError):
        make_provider("nope")


class _FakeAnthropicMessages:
    def __init__(self, parsed):
        self._parsed = parsed
        self.calls: list[dict] = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return type("Resp", (), {"parsed_output": self._parsed})()


class _FakeAnthropicClient:
    def __init__(self, parsed):
        self.messages = _FakeAnthropicMessages(parsed)


async def test_anthropic_provider_parse_uses_messages_parse():
    parsed = MatchAnalysis(score=70, reasons=["a"], gaps=["b"])
    client = _FakeAnthropicClient(parsed)
    result = await AnthropicProvider().parse("prompt", MatchAnalysis, client=client)
    assert result.score == 70
    # Anthropic 走原生 structured outputs（output_format），非 json_object
    assert client.messages.calls[0]["output_format"] is MatchAnalysis


def test_make_provider_supports_foundry():
    assert isinstance(make_provider("foundry"), FoundryProvider)


async def test_foundry_provider_parse_uses_messages_parse_and_model():
    parsed = MatchAnalysis(score=88, reasons=[], gaps=[])
    client = _FakeAnthropicClient(parsed)
    result = await FoundryProvider().parse("prompt", MatchAnalysis, client=client)
    assert result.score == 88
    sent = client.messages.calls[0]
    # Foundry 也走原生 Messages API，model 用 deployment 名稱
    assert sent["output_format"] is MatchAnalysis
    assert sent["model"] == get_settings().foundry_model
