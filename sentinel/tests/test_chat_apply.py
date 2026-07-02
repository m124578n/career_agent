from career_sentinel import chat, store
from career_sentinel.models import ChatMessage, ChatState, ResumeState, SuggestedUpdate


def _conn(tmp_path):
    return store.connect(tmp_path / "db.sqlite")


def test_apply_set_scalar_and_lists(tmp_path):
    conn = _conn(tmp_path)
    assert chat.apply_update(conn, SuggestedUpdate(field="target_title", op="set", value="後端工程師")).ok
    assert chat.apply_update(conn, SuggestedUpdate(field="expected_salary", op="set", value=900000)).ok
    assert chat.apply_update(conn, SuggestedUpdate(field="locations", op="set", value=["台北"])).ok
    assert chat.apply_update(conn, SuggestedUpdate(field="watched_companies", op="set", value=["台積電"])).ok
    assert store.load_resume(conn).target_title == "後端工程師"
    assert store.load_resume(conn).expected_salary == 900000
    assert store.load_preferences(conn).locations == ["台北"]
    assert store.load_settings(conn).watched_companies == ["台積電"]


def test_apply_salary_non_numeric_fails(tmp_path):
    r = chat.apply_update(_conn(tmp_path), SuggestedUpdate(field="expected_salary", op="set", value="九十萬"))
    assert not r.ok


def test_apply_whitelist_rejects(tmp_path):
    conn = _conn(tmp_path)
    assert not chat.apply_update(conn, SuggestedUpdate(field="resume_text", op="set", value="x")).ok
    assert not chat.apply_update(conn, SuggestedUpdate(field="diagnosis", op="set", value="x")).ok
    assert not chat.apply_update(conn, SuggestedUpdate(field="target_title", op="remember", value="x")).ok


def test_apply_replace_snippet(tmp_path):
    conn = _conn(tmp_path)
    store.save_resume(conn, ResumeState(resume_text="Python 三年經驗"))
    ok = chat.apply_update(conn, SuggestedUpdate(
        field="resume_text", op="replace_snippet", old="三年", new="五年"))
    assert ok.ok
    assert store.load_resume(conn).resume_text == "Python 五年經驗"
    miss = chat.apply_update(conn, SuggestedUpdate(
        field="resume_text", op="replace_snippet", old="不存在的片段", new="x"))
    assert not miss.ok and "手動" in miss.message


def test_apply_append_section(tmp_path):
    conn = _conn(tmp_path)
    store.save_resume(conn, ResumeState(resume_text="經歷 A"))
    assert chat.apply_update(conn, SuggestedUpdate(
        field="resume_text", op="append_section", value="技能：Bicep")).ok
    assert store.load_resume(conn).resume_text == "經歷 A\n\n技能：Bicep"


def test_apply_remember_appends_memory(tmp_path):
    conn = _conn(tmp_path)
    assert chat.apply_update(conn, SuggestedUpdate(field="memory", op="remember", value="不想進博弈業")).ok
    facts = store.load_memory(conn).facts
    assert len(facts) == 1 and facts[0].text == "不想進博弈業" and facts[0].created_at


def _mk_state(n: int) -> ChatState:
    return ChatState(messages=[
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"m{i}") for i in range(n)
    ])


def test_compact_below_threshold_noop(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    called = {"n": 0}
    monkeypatch.setattr(chat.llm, "chat_stream", lambda *a, **k: called.__setitem__("n", 1) or iter([]))
    state = _mk_state(30)
    assert chat.maybe_compact(conn, state) == state
    assert called["n"] == 0


def test_compact_over_threshold_summarizes_and_trims(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(chat.llm, "chat_stream", lambda *a, **k: iter(["新", "摘要"]))
    state = _mk_state(31)
    store.save_chat(conn, state)
    out = chat.maybe_compact(conn, state)
    assert out.summary == "新摘要"
    assert len(out.messages) == chat.COMPACT_KEEP
    assert out.messages[-1].content == "m30"
    assert store.load_chat(conn) == out  # 已持久化


def test_compact_llm_failure_keeps_everything(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    def boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(chat.llm, "chat_stream", boom)
    state = _mk_state(31)
    store.save_chat(conn, state)
    out = chat.maybe_compact(conn, state)
    assert out == state  # 失敗跳過、不丟訊息
    assert store.load_chat(conn) == state
