from job_tracker.llm import usage


def _obj(**kw):
    return type("U", (), kw)()


def test_normalize_openai_shape():
    raw = _obj(prompt_tokens=100, completion_tokens=40, total_tokens=140)
    rec = usage.normalize("openrouter", "gpt-4o-mini", "parse", raw)
    assert rec["input_tokens"] == 100
    assert rec["output_tokens"] == 40
    assert rec["total_tokens"] == 140
    assert rec["provider"] == "openrouter"


def test_normalize_anthropic_shape_computes_total():
    raw = _obj(input_tokens=200, output_tokens=60)  # 無 total_tokens
    rec = usage.normalize("foundry", "claude-sonnet-4-6", "parse", raw)
    assert rec["input_tokens"] == 200
    assert rec["output_tokens"] == 60
    assert rec["total_tokens"] == 260


def test_normalize_none_returns_none():
    assert usage.normalize("x", "y", "parse", None) is None


async def test_record_calls_sink():
    captured: list[dict] = []

    async def sink(rec: dict):
        captured.append(rec)

    usage.set_sink(sink)
    try:
        raw = _obj(input_tokens=10, output_tokens=5)
        await usage.record("foundry", "m", "complete", raw)
    finally:
        usage.set_sink(None)

    assert len(captured) == 1
    assert captured[0]["total_tokens"] == 15


async def test_record_noop_without_sink():
    usage.set_sink(None)
    # 無 sink 不應拋錯
    await usage.record("foundry", "m", "parse", _obj(input_tokens=1, output_tokens=1))
