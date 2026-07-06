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
    assert store.load_preferences(conn).target_title == "後端工程師"
    assert store.load_preferences(conn).expected_salary == 900000
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


def test_apply_remember_dedupes_and_rejects_empty(tmp_path):
    conn = _conn(tmp_path)
    assert chat.apply_update(conn, SuggestedUpdate(field="memory", op="remember", value="不想進博弈業")).ok
    assert not chat.apply_update(conn, SuggestedUpdate(field="memory", op="remember", value="不想進博弈業")).ok
    assert not chat.apply_update(conn, SuggestedUpdate(field="memory", op="remember", value="")).ok
    assert len(store.load_memory(conn).facts) == 1


def test_apply_forget(tmp_path):
    conn = _conn(tmp_path)
    chat.apply_update(conn, SuggestedUpdate(field="memory", op="remember", value="只想找台北"))
    assert chat.apply_update(conn, SuggestedUpdate(field="memory", op="forget", value="只想找台北")).ok
    assert store.load_memory(conn).facts == []
    assert not chat.apply_update(conn, SuggestedUpdate(field="memory", op="forget", value="不存在")).ok


def _mk_mem(n):
    from career_sentinel.models import MemoryFact, MemoryState
    return MemoryState(facts=[MemoryFact(text=f"f{i}", created_at="t") for i in range(n)])


def test_curate_below_threshold_noop(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    store.save_memory(conn, _mk_mem(12))
    called = {"n": 0}
    monkeypatch.setattr(chat.llm, "parse_json", lambda *a, **k: called.__setitem__("n", 1))
    chat.maybe_curate_memory(conn)
    assert called["n"] == 0
    assert len(store.load_memory(conn).facts) == 12


def test_curate_over_threshold_merges(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    store.save_memory(conn, _mk_mem(13))
    monkeypatch.setattr(
        chat.llm, "parse_json",
        lambda *a, **k: chat.CuratedFacts(facts=["f0", "合併後的新事實"]),
    )
    chat.maybe_curate_memory(conn)
    facts = store.load_memory(conn).facts
    assert [f.text for f in facts] == ["f0", "合併後的新事實"]
    assert facts[0].created_at == "t"   # 既有條目保留原時間
    assert facts[1].created_at != "t"   # 合併新條目給現在時間


def test_curate_failure_or_empty_keeps_original(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    store.save_memory(conn, _mk_mem(13))
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(chat.llm, "parse_json", boom)
    chat.maybe_curate_memory(conn)
    assert len(store.load_memory(conn).facts) == 13
    monkeypatch.setattr(chat.llm, "parse_json", lambda *a, **k: chat.CuratedFacts(facts=[]))
    chat.maybe_curate_memory(conn)
    assert len(store.load_memory(conn).facts) == 13


def test_suggested_update_payload_roundtrip():
    u = SuggestedUpdate(field="job_offer", op="set", payload={"code": "x", "salary_year": 100})
    assert u.payload["code"] == "x"
    u2 = SuggestedUpdate(field="target_title", op="set", value="後端")
    assert u2.payload is None


def test_apply_track_adds_job(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={
        "code": "abc12", "company": "甲", "title": "後端",
        "url": "https://www.104.com.tw/job/abc12", "salary": "6萬"}))
    assert r.ok
    tj = store.get_tracked_job(conn, "abc12")
    assert tj is not None and tj.state == "interested" and tj.company == "甲" and tj.salary == "6萬"


def test_apply_job_offer_sets_state_and_detail(tmp_path):
    from career_sentinel.models import OfferDetail
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="job_offer", op="set", payload={
        "code": "of1", "salary_year": 1200000, "location": "台北", "level": "資深"}))
    assert r.ok
    tj = store.get_tracked_job(conn, "of1")
    assert tj.state == "offer"
    parsed = OfferDetail.model_validate_json(tj.offer_json)
    assert parsed.salary_year == 1200000 and parsed.location == "台北"


def test_apply_job_reject_and_reset(tmp_path):
    conn = _conn(tmp_path)
    chat.apply_update(conn, SuggestedUpdate(field="job_offer", op="set", payload={"code": "j1", "salary_year": 100}))
    assert chat.apply_update(conn, SuggestedUpdate(field="job_reject", op="set", payload={"code": "j1"})).ok
    assert store.get_tracked_job(conn, "j1").state == "rejected"
    assert store.get_tracked_job(conn, "j1").offer_json == ""
    assert chat.apply_update(conn, SuggestedUpdate(field="job_reset", op="set", payload={"code": "j1"})).ok
    assert store.get_tracked_job(conn, "j1").state == "interested"


def test_apply_untrack_removes(tmp_path):
    conn = _conn(tmp_path)
    chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={"code": "u1", "company": "甲"}))
    assert chat.apply_update(conn, SuggestedUpdate(field="untrack", op="set", payload={"code": "u1"})).ok
    assert store.get_tracked_job(conn, "u1") is None


def test_apply_pipeline_action_missing_code(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={"company": "甲"}))
    assert not r.ok and "代碼" in r.message


def test_apply_job_offer_bad_salary_is_clean_error(tmp_path):
    # LLM 若把 salary_year 給成不可轉型字串，回乾淨 ApplyResult(ok=False)、不冒 500
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="job_offer", op="set",
                                                payload={"code": "b1", "salary_year": "一百二十萬"}))
    assert not r.ok and "格式" in r.message
    assert store.get_tracked_job(conn, "b1") is None  # 未誤寫


def test_apply_track_preserves_offer_terminal(tmp_path):
    # 對已 offer 職缺送 track（走 merge）→ 防降級：state 仍 offer、offer_json 保留（SP20 修正）
    from career_sentinel.models import OfferDetail
    conn = _conn(tmp_path)
    store.set_tracked_state(conn, "t1", "offer", offer=OfferDetail(salary_year=999))
    chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={"code": "t1", "company": "甲"}))
    tj = store.get_tracked_job(conn, "t1")
    assert tj.state == "offer" and tj.offer_json != ""


def test_parse_suggestions_tailor():
    tail = ('<suggestions>{"items":[{"field":"tailor","op":"run",'
            '"payload":{"code":"abc12","company":"甲","title":"後端"}}]}</suggestions>')
    items = chat.parse_suggestions(tail)
    assert len(items) == 1
    assert items[0].field == "tailor" and items[0].op == "run"
    assert items[0].payload["code"] == "abc12" and items[0].payload["title"] == "後端"


def test_apply_update_rejects_tailor(tmp_path):
    # tailor 不走 apply_update（前端直接打 /api/tailor）；誤打到 apply 應落 fallback ok=False
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="tailor", op="run", payload={"code": "x"}))
    assert not r.ok


def test_apply_update_rejects_negotiate(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="negotiate", op="run", payload={"code": "x"}))
    assert not r.ok


def test_apply_interview_note_appends(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="interview_note", op="set", payload={
        "code": "abc12", "when": "2026-07-10 一面", "content": "問系統設計"}))
    assert r.ok
    import json
    notes = json.loads(store.get_tracked_job(conn, "abc12").interviews_json)
    assert len(notes) == 1 and notes[0]["when"] == "2026-07-10 一面" and notes[0]["content"] == "問系統設計"


def test_apply_interview_note_missing_code(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="interview_note", op="set", payload={"content": "x"}))
    assert not r.ok and "代碼" in r.message
