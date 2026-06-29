from career_sentinel import diagnosis, llm
from career_sentinel.config import LlmSettings


def test_build_prompt_contains_target_and_resume():
    p = diagnosis.build_prompt("我會 Python", "後端工程師", 60000)
    assert "後端工程師" in p
    assert "我會 Python" in p
    assert "60000" in p


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": '{"strengths":["熟 Python"],"gaps":["缺雲端"]}'}}]}


class _FakeClient:
    def post(self, url, **kw):
        return _FakeResp()


def test_diagnose_with_fake_client(monkeypatch):
    # config 會載入 .env，實際 provider 可能是 foundry；測試固定走 openai 路徑 + 假 client
    monkeypatch.setattr(llm, "llm_provider", lambda: "openai")
    monkeypatch.setattr(llm, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    out = diagnosis.diagnose("我會 Python", "後端工程師", 60000, client=_FakeClient())
    assert out.strengths == ["熟 Python"]
    assert out.gaps == ["缺雲端"]
