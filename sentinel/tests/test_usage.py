from types import SimpleNamespace

from career_sentinel import store, usage


def test_price_for_sonnet_and_default():
    assert usage._price_for("claude-sonnet-4-5")["in"] == 3.00
    assert usage._price_for("some-unknown-model") == usage._PRICING["default"]


def test_cost_of_known_tokens():
    # 1M input @3, 1M output @15, 1M cache_read @0.30, 1M cache_write @3.75
    cost = usage.cost_of("sonnet", 1_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert abs(cost - (3.00 + 15.00 + 0.30 + 3.75)) < 1e-9


def test_normalize_anthropic_object():
    raw = SimpleNamespace(
        input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=20, cache_read_input_tokens=10,
    )
    assert usage.normalize(raw) == {"input": 100, "output": 50, "cache_read": 10, "cache_write": 20}


def test_normalize_openai_dict_with_cache():
    raw = {"prompt_tokens": 100, "completion_tokens": 40,
           "prompt_tokens_details": {"cached_tokens": 30}}
    # OpenAI prompt_tokens 含 cache：input = 100 - 30
    assert usage.normalize(raw) == {"input": 70, "output": 40, "cache_read": 30, "cache_write": 0}


def test_normalize_openai_dict_no_cache():
    raw = {"prompt_tokens": 80, "completion_tokens": 20}
    assert usage.normalize(raw) == {"input": 80, "output": 20, "cache_read": 0, "cache_write": 0}


def test_normalize_none():
    assert usage.normalize(None) == {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def test_record_summary_reset_roundtrip(tmp_path):
    db = tmp_path / "u.db"
    usage.record("履歷健檢", "claude-sonnet-4-5",
                 SimpleNamespace(input_tokens=1_000_000, output_tokens=0,
                                 cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    usage.record("JD比對", "claude-sonnet-4-5",
                 SimpleNamespace(input_tokens=0, output_tokens=1_000_000,
                                 cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    usage.record("JD比對", "claude-sonnet-4-5",
                 SimpleNamespace(input_tokens=1_000_000, output_tokens=0,
                                 cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    conn = store.connect(db)
    s = usage.summary(conn)
    assert s["total_tokens"] == 3_000_000
    assert abs(s["total_usd"] - (3.00 + 15.00 + 3.00)) < 1e-9
    # by_feature 依 usd 降冪：JD比對(18.0, 2 次) 在 履歷健檢(3.0, 1 次) 前
    assert [f["feature"] for f in s["by_feature"]] == ["JD比對", "履歷健檢"]
    assert s["by_feature"][0]["calls"] == 2
    usage.reset(conn)
    assert usage.summary(conn)["total_tokens"] == 0
    conn.close()


def test_record_best_effort_swallows(monkeypatch, tmp_path):
    def boom(_raw):
        raise ValueError("boom")
    monkeypatch.setattr(usage, "normalize", boom)
    # 不得往上拋
    usage.record("x", "m", object(), db=tmp_path / "u.db")
