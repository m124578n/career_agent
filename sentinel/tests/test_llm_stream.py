import pytest

from career_sentinel import llm


class _FakeResp:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeHttp:
    def __init__(self, lines):
        self._lines = lines
        self.captured = None

    def stream(self, method, url, **kw):
        self.captured = {"method": method, "url": url, **kw}
        return _FakeResp(self._lines)


def test_openai_chat_stream_yields_deltas(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    fake = _FakeHttp([
        'data: {"choices":[{"delta":{"content":"你"}}]}',
        'data: {"choices":[{"delta":{"content":"好"}}]}',
        "data: {\"choices\":[]}",  # keepalive：空 choices 要略過
        "data: [DONE]",
    ])
    out = list(llm.chat_stream([{"role": "user", "content": "hi"}], system="s", client=fake))
    assert out == ["你", "好"]
    assert fake.captured["json"]["stream"] is True
    sys_msg = fake.captured["json"]["messages"][0]
    assert sys_msg["role"] == "system"
    assert sys_msg["content"].startswith("s\n\n")  # 原 system 保留
    assert "今天日期：" in sys_msg["content"]         # 自動注入今天日期


class _FakeAnthropicStream:
    def __init__(self, chunks):
        self.text_stream = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeAnthropicMessages:
    def __init__(self, chunks):
        self._chunks = chunks
        self.captured = None

    def stream(self, **kw):
        self.captured = kw
        return _FakeAnthropicStream(self._chunks)


class _FakeAnthropic:
    def __init__(self, chunks):
        self.messages = _FakeAnthropicMessages(chunks)


def test_foundry_chat_stream_yields_deltas(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    fake = _FakeAnthropic(["嗨", "！"])
    out = list(llm.chat_stream([{"role": "user", "content": "hi"}], system="s", client=fake))
    assert out == ["嗨", "！"]
    assert fake.messages.captured["system"].startswith("s\n\n")
    assert "今天日期：" in fake.messages.captured["system"]
    assert fake.messages.captured["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_stream_no_key_raises(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        list(llm.chat_stream([{"role": "user", "content": "hi"}]))
