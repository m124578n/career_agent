import pytest

from career_sentinel import config, llm
from career_sentinel.config import FoundrySettings, LlmSettings
from career_sentinel.models import ResumeDiagnosis


# ---- OpenAI 相容路徑 ----
class _OpenAIResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": '{"strengths":["A"],"gaps":["B"]}'}}]}


class _OpenAIClient:
    def __init__(self):
        self.captured = {}

    def post(self, url, **kw):
        self.captured["url"] = url
        self.captured["json"] = kw["json"]
        return _OpenAIResp()


# ---- Foundry（Anthropic Messages）路徑 ----
class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FoundryResp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FoundryClient:
    """模擬 anthropic AnthropicFoundry：client.messages.create(...)。"""

    def __init__(self):
        self.messages = self
        self.captured = {}

    def create(self, **kw):
        self.captured = kw
        return _FoundryResp('```json\n{"strengths":["F"],"gaps":["G"]}\n```')


def test_parse_json_no_provider_raises(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "")
    with pytest.raises(RuntimeError):
        llm.parse_json("p", ResumeDiagnosis)


def test_parse_json_openai_path(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "openai")
    monkeypatch.setattr(llm, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    fc = _OpenAIClient()
    out = llm.parse_json("p", ResumeDiagnosis, system="s", client=fc)
    assert out.strengths == ["A"] and out.gaps == ["B"]
    assert fc.captured["url"] == "https://x/v1/chat/completions"
    assert fc.captured["json"]["response_format"] == {"type": "json_object"}


def test_parse_json_foundry_path(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "foundry")
    monkeypatch.setattr(llm, "foundry_settings", lambda: FoundrySettings("k", "https://f/anthropic", "claude-sonnet-4-6"))
    fc = _FoundryClient()
    out = llm.parse_json("p", ResumeDiagnosis, system="s", client=fc)
    assert out.strengths == ["F"] and out.gaps == ["G"]  # 含 markdown 圍欄仍正確抽出
    assert fc.captured["model"] == "claude-sonnet-4-6"
