import json

import pytest

from career_sentinel import tailor
from career_sentinel.models import JobDetail, TailoredApplication

_PAYLOAD = json.dumps({
    "resume_tips": ["強調 Python 五年經驗"],
    "resume_adjustments": ["把雲端經驗提前"],
    "missing_keywords": ["Kubernetes"],
    "cover_letter": "敬啟者：我對貴公司的後端職缺深感興趣……",
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


def _jd():
    return JobDetail(title="後端工程師", company="甲公司", description="需 Python 與雲端",
                     work_exp="3 年", education="大學", specialties=["Python", "AWS"])


def _openai_env(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    monkeypatch.setenv("LLM_MODEL", "m")


def test_tailor_parses(monkeypatch):
    _openai_env(monkeypatch)
    fake = _FakeHttp(_PAYLOAD)
    r = tailor.tailor_application("Python 五年", "後端工程師", _jd(), client=fake)
    assert r.resume_tips == ["強調 Python 五年經驗"]
    assert r.missing_keywords == ["Kubernetes"]
    assert r.cover_letter.startswith("敬啟者")
    # prompt 帶履歷全文與 JD
    sent = fake.captured["json"]["messages"][-1]["content"]
    assert "Python 五年" in sent and "後端工程師" in sent and "甲公司" in sent


def test_tailor_bad_json_raises(monkeypatch):
    _openai_env(monkeypatch)
    with pytest.raises(Exception):
        tailor.tailor_application("履歷", "後端", _jd(), client=_FakeHttp("沒有 JSON"))


def test_tailored_application_defaults():
    t = TailoredApplication()
    assert t.resume_tips == [] and t.cover_letter == "" and t.company == ""
