import json
from datetime import datetime, timedelta

import pytest

from career_sentinel import research
from career_sentinel.models import CompanyResearch

_PAYLOAD = json.dumps({
    "summary": "整體評價正面",
    "pros": ["福利好"], "cons": ["工時長"],
    "salary_notes": "高於同業", "interview_notes": "流程長",
    "risk_level": "low",
    "sources": [{"title": "面試趣", "url": "https://interview.tw/x"}],
}, ensure_ascii=False)


class _FakeResp:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeHttp:
    def __init__(self, content):
        self._content = content
        self.captured = None

    def post(self, url, **kw):
        self.captured = {"url": url, **kw}
        return _FakeResp(self._content)


def _openai_env(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    monkeypatch.setenv("LLM_MODEL", "m")


def test_research_openai_parses(monkeypatch):
    _openai_env(monkeypatch)
    fake = _FakeHttp(_PAYLOAD)
    r = research.research_company("台積電", client=fake)
    assert r.company == "台積電"
    assert r.risk_level == "low" and r.pros == ["福利好"]
    assert r.researched_at  # 寫入當下時間
    assert fake.captured["json"]["model"] == "m:online"
    assert "台積電" in fake.captured["json"]["messages"][0]["content"]


def test_research_bad_json_raises(monkeypatch):
    _openai_env(monkeypatch)
    with pytest.raises(Exception):
        research.research_company("台積電", client=_FakeHttp("查不到喔（無 JSON）"))


def test_research_no_key_raises(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        research.research_company("台積電")


class _FakeAnthropicText:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeAnthropicResp:
    def __init__(self, text):
        self.content = [_FakeAnthropicText(text)]


class _FakeAnthropicMessages:
    def __init__(self, text):
        self._text = text
        self.captured = None

    def create(self, **kw):
        self.captured = kw
        return _FakeAnthropicResp(self._text)


class _FakeAnthropic:
    def __init__(self, text):
        self.messages = _FakeAnthropicMessages(text)


def test_research_foundry_uses_web_search_tool(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    fake = _FakeAnthropic(_PAYLOAD)
    r = research.research_company("台積電", client=fake)
    assert r.risk_level == "low"
    tools = fake.messages.captured["tools"]
    assert tools and tools[0]["name"] == "web_search"


def _stamp(dt):
    return dt.isoformat(timespec="seconds")


def test_is_fresh_ttl_boundary():
    now = datetime(2026, 7, 10, 12, 0, 0)
    fresh = CompanyResearch(researched_at=_stamp(now - timedelta(days=6, hours=23)))
    stale = CompanyResearch(researched_at=_stamp(now - timedelta(days=7, seconds=1)))
    assert research.is_fresh(fresh, now=now) is True
    assert research.is_fresh(stale, now=now) is False
    assert research.is_fresh(CompanyResearch(researched_at=""), now=now) is False
    assert research.is_fresh(CompanyResearch(researched_at="not-a-date"), now=now) is False
