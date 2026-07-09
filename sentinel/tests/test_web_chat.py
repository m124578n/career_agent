import json

from fastapi.testclient import TestClient

from career_sentinel import chat as chatmod, config, llm, pipeline, store
from career_sentinel.models import ChatMessage, ChatState, MemoryFact, MemoryState, OfferDetail
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _fake_stream(chunks):
    def fake(messages, *, system=None, client=None, feature=""):
        return iter(chunks)
    return fake


def test_chat_requires_llm_key(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    r = _client(tmp_path).post("/api/chat", json={"message": "hi"})
    assert r.status_code == 400


def test_chat_streams_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setattr(llm, "chat_stream", _fake_stream([
        "好的，", "已了解",
        '<suggestions>{"items":[{"field":"expected_salary","op":"set","value":900000},'
        '{"field":"memory","op":"remember","value":"不想進博弈業"}]}</suggestions>',
    ]))
    c = _client(tmp_path)
    r = c.post("/api/chat", json={"message": "薪資改90萬，我不想進博弈業"})
    assert r.status_code == 200
    evs = _events(r.text)
    kinds = [k for k, _ in evs]
    assert kinds == ["delta", "delta", "suggestions", "remembered", "done"]
    assert "".join(d["text"] for k, d in evs if k == "delta") == "好的，已了解"
    sugg = dict(evs)["suggestions"]["items"]
    assert len(sugg) == 1 and sugg[0]["field"] == "expected_salary"  # remember 不進卡片
    assert dict(evs)["remembered"]["facts"] == ["不想進博弈業"]
    # 持久化：乾淨訊息（無標記）＋memory 自動寫入
    conn = store.connect(tmp_path / "db.sqlite")
    st = store.load_chat(conn)
    assert [m.content for m in st.messages] == ["薪資改90萬，我不想進博弈業", "好的，已了解"]
    assert store.load_memory(conn).facts[0].text == "不想進博弈業"


def test_chat_error_event_and_no_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    def boom(messages, *, system=None, client=None, feature=""):
        yield "半句"
        raise RuntimeError("connection reset")
    monkeypatch.setattr(llm, "chat_stream", boom)
    c = _client(tmp_path)
    evs = _events(c.post("/api/chat", json={"message": "hi"}).text)
    assert evs[0][0] == "delta" and evs[-1][0] == "error"
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_chat(conn).messages == []  # 中斷不持久化


def test_chat_apply_endpoint(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/chat/apply", json={"field": "target_title", "op": "set", "value": "後端"})
    assert r.status_code == 200 and r.json()["ok"] is True
    r2 = c.post("/api/chat/apply", json={"field": "diagnosis", "op": "set", "value": "x"})
    assert r2.status_code == 400
    r3 = c.post("/api/chat/apply", json={
        "field": "resume_text", "op": "replace_snippet", "old": "沒有這段", "new": "x"})
    assert r3.status_code == 200 and r3.json()["ok"] is False


def test_chat_get_and_clear_keeps_memory(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_chat(conn, ChatState(summary="s", messages=[ChatMessage(role="user", content="a")]))
    store.save_memory(conn, MemoryState(facts=[MemoryFact(text="f", created_at="t")]))
    c = _client(tmp_path)
    body = c.get("/api/chat").json()
    assert body["summary"] == "s" and body["messages"][0]["content"] == "a"
    assert body["memory"][0]["text"] == "f"
    assert c.delete("/api/chat").json() == {"ok": True}
    body2 = c.get("/api/chat").json()
    assert body2["messages"] == [] and body2["summary"] == ""
    assert body2["memory"][0]["text"] == "f"  # 清空對話不動 memory


def test_memory_delete(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_memory(conn, MemoryState(facts=[
        MemoryFact(text="f0", created_at="t"), MemoryFact(text="f1", created_at="t")]))
    c = _client(tmp_path)
    assert c.delete("/api/memory/0").json() == {"ok": True}
    assert [f["text"] for f in c.get("/api/chat").json()["memory"]] == ["f1"]
    assert c.delete("/api/memory/9").status_code == 404


def test_chat_memory_forget_and_dedupe(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_memory(conn, MemoryState(facts=[
        MemoryFact(text="只想找台北的工作", created_at="t"),
        MemoryFact(text="不想進博弈業", created_at="t"),
    ]))
    monkeypatch.setattr(llm, "chat_stream", _fake_stream([
        "更新好了",
        '<suggestions>{"items":['
        '{"field":"memory","op":"forget","value":"只想找台北的工作"},'
        '{"field":"memory","op":"remember","value":"雙北都可以"},'
        '{"field":"memory","op":"remember","value":"不想進博弈業"}'
        ']}</suggestions>',
    ]))
    c = _client(tmp_path)
    evs = _events(c.post("/api/chat", json={"message": "台北或新北都行"}).text)
    d = dict(evs)
    assert d["remembered"]["facts"] == ["雙北都可以"]  # 重複的不再發徽章
    assert d["forgot"]["facts"] == ["只想找台北的工作"]
    assert "suggestions" not in d  # memory 項目不成卡片
    texts = [f.text for f in store.load_memory(store.connect(tmp_path / "db.sqlite")).facts]
    assert texts == ["不想進博弈業", "雙北都可以"]


def test_chat_foundry_streams_jobs_events(tmp_path, monkeypatch):
    from career_sentinel import chat as chatmod
    from career_sentinel.models import RecommendedJob, Settings
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_settings(conn, Settings(watched_companies=["公司0"]))

    def fake_stream(messages, *, system, db_path=None, **kw):
        yield {"type": "text", "text": "我來搜尋"}
        yield {"type": "jobs", "keyword": "python 後端", "items": [
            RecommendedJob(code="c0", url="u0", title="職缺0", company="公司0", salary="月薪 5萬"),
            RecommendedJob(code="c1", url="u1", title="職缺1", company="公司1", salary="月薪 6萬"),
        ]}
        yield {"type": "text", "text": "找到了"}

    monkeypatch.setattr(chatmod, "stream_with_tools", fake_stream)
    c = _client(tmp_path)
    evs = _events(c.post("/api/chat", json={"message": "幫我找 python 後端"}).text)
    kinds = [k for k, _ in evs]
    assert kinds == ["delta", "jobs", "delta", "done"]
    jobs = dict(evs)["jobs"]
    assert jobs["keyword"] == "python 後端"
    assert jobs["items"][0]["is_watched"] is True   # 關注公司標記
    assert jobs["items"][1]["is_watched"] is False
    assert set(jobs["items"][0].keys()) == {"code", "url", "title", "company", "salary", "is_watched"}
    # 持久化的 assistant 訊息只含文字
    st = store.load_chat(store.connect(tmp_path / "db.sqlite"))
    assert st.messages[-1].content == "我來搜尋找到了"


def test_chat_openai_path_unchanged(tmp_path, monkeypatch):
    # openai 路徑仍走 llm.chat_stream（無工具），行為與 SP8 相同
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setattr(llm, "chat_stream", _fake_stream(["hi"]))
    evs = _events(_client(tmp_path).post("/api/chat", json={"message": "hi"}).text)
    assert [k for k, _ in evs] == ["delta", "done"]


def test_export_md(tmp_path):
    from career_sentinel.models import JobPreferences, ResumeState
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_resume(conn, ResumeState(resume_text="Python 五年"))
    store.save_preferences(conn, JobPreferences(target_title="後端工程師", expected_salary=90000))
    store.save_memory(conn, MemoryState(facts=[MemoryFact(text="不想進博弈業", created_at="t")]))
    r = _client(tmp_path).get("/api/export")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert "attachment" in r.headers["content-disposition"]
    for needle in ("後端工程師", "90000", "不想進博弈業", "Python 五年", "求職檔案"):
        assert needle in r.text


def test_chat_injects_pipeline_summary_and_db_path(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=1200000))

    monkeypatch.setattr(config, "llm_provider", lambda: "foundry")
    captured = {}

    def fake_stream(messages, *, system, db_path=None, **kw):
        captured["system"] = system
        captured["db_path"] = db_path
        yield {"type": "text", "text": "好"}

    monkeypatch.setattr(chatmod, "stream_with_tools", fake_stream)
    c = TestClient(webapp.create_app(db_path=db))
    r = c.post("/api/chat", json={"message": "我的管道現況"})
    assert r.status_code == 200
    assert "目前求職管道" in captured["system"]
    assert "of1" in captured["system"]         # 管道摘要含該職缺 code
    assert captured["db_path"] == db           # db_path 傳進工具迴圈


def test_chat_pipeline_summary_best_effort(tmp_path, monkeypatch):
    # build_pipeline 爆掉時 system 仍可組（pipe_summary=""），聊天不中斷
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    monkeypatch.setattr(config, "llm_provider", lambda: "foundry")
    monkeypatch.setattr(pipeline, "build_pipeline",
                        lambda conn: (_ for _ in ()).throw(RuntimeError("boom")))
    captured = {}

    def fake_stream(messages, *, system, db_path=None, **kw):
        captured["system"] = system
        yield {"type": "text", "text": "好"}

    monkeypatch.setattr(chatmod, "stream_with_tools", fake_stream)
    c = TestClient(webapp.create_app(db_path=db))
    r = c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert "管道目前無職缺" in captured["system"]  # 失敗退回佔位字
