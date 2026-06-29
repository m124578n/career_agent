from career_sentinel import llm, match
from career_sentinel.config import LlmSettings
from career_sentinel.models import JobDetail


def test_build_prompt_contains_resume_and_jd():
    jd = JobDetail(title="全端工程師", company="範例", description="需要 Python/FastAPI", specialties=["Python", "FastAPI"])
    p = match.build_prompt("我會 Python", "後端工程師", jd)
    assert "後端工程師" in p
    assert "我會 Python" in p
    assert "Python/FastAPI" in p
    assert "FastAPI" in p


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": '{"score":80,"reasons":["熟 Python"],"gaps":["缺雲端"]}'}}]}


class _FakeClient:
    def post(self, url, **kw):
        return _FakeResp()


def test_match_with_fake_client(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "openai")
    monkeypatch.setattr(llm, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    jd = JobDetail(title="全端工程師", description="Python")
    out = match.match("我會 Python", "後端工程師", jd, client=_FakeClient())
    assert out.score == 80
    assert out.reasons == ["熟 Python"]
    assert out.gaps == ["缺雲端"]
