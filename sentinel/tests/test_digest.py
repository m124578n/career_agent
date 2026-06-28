from career_sentinel import digest
from career_sentinel.config import LlmSettings
from career_sentinel.models import Diff, Snapshot, Viewer


def test_build_prompt_mentions_new_viewer():
    d = Diff(new_viewers=[Viewer(company="台積電", job_title="後端", viewed_at="2026-06-28")])
    text = digest.build_prompt(d, Snapshot())
    assert "台積電" in text
    assert "後端" in text


def test_summarize_no_change_uses_local_fallback(monkeypatch):
    monkeypatch.setattr(digest, "llm_settings", lambda: LlmSettings("", "", "m"))
    out = digest.summarize(Diff(), Snapshot())
    assert "沒有新變化" in out


def test_summarize_no_key_uses_local_fallback(monkeypatch):
    monkeypatch.setattr(digest, "llm_settings", lambda: LlmSettings("https://x/v1", "", "m"))
    d = Diff(new_viewers=[Viewer(company="台積電", job_title="後端", viewed_at="t")])
    out = digest.summarize(d, Snapshot())
    assert "台積電" in out  # 後援直接列出變化


def test_summarize_calls_llm_when_configured(monkeypatch):
    monkeypatch.setattr(digest, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "今日彙整：有人看你"}}]}

    class FakeClient:
        def post(self, url, **kw):
            captured["url"] = url
            captured["json"] = kw["json"]
            return FakeResp()

    d = Diff(new_viewers=[Viewer(company="A", job_title="x", viewed_at="t")])
    out = digest.summarize(d, Snapshot(), client=FakeClient())
    assert out == "今日彙整：有人看你"
    assert captured["url"] == "https://x/v1/chat/completions"
    assert captured["json"]["model"] == "m"
