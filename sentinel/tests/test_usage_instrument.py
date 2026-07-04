from types import SimpleNamespace

from career_sentinel import diagnosis, llm, usage
from career_sentinel.models import ResumeDiagnosis


class _FakeFoundry:
    """假 AnthropicFoundry：messages.create 回帶 usage 的假 resp。"""
    def __init__(self, text, usage_obj):
        self._text = text
        self._usage = usage_obj
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._text)],
            usage=self._usage,
        )


def test_parse_json_foundry_records_usage(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "foundry")
    monkeypatch.setattr(llm, "foundry_settings",
                        lambda: SimpleNamespace(api_key="k", base_url="b", model="claude-sonnet-4-5"))
    captured = {}
    monkeypatch.setattr(usage, "record",
                        lambda feature, model, raw, **kw: captured.update(
                            feature=feature, model=model, raw=raw))
    fake = _FakeFoundry('{"strengths": ["a"], "gaps": ["b"]}',
                        SimpleNamespace(input_tokens=10, output_tokens=5,
                                        cache_creation_input_tokens=0, cache_read_input_tokens=0))
    out = diagnosis.diagnose("履歷", "工程師", None, client=fake)
    assert isinstance(out, ResumeDiagnosis)          # 回傳值不變
    assert out.strengths == ["a"]
    assert captured["feature"] == "履歷健檢"           # feature 正確
    assert captured["model"] == "claude-sonnet-4-5"   # model 正確
    assert captured["raw"].input_tokens == 10
