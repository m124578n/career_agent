import json

from fastapi.testclient import TestClient

from career_sentinel import llm, store
from career_sentinel.models import ChatMessage, ChatState, MemoryFact, MemoryState
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
    def fake(messages, *, system=None, client=None):
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
    def boom(messages, *, system=None, client=None):
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
