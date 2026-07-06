from fastapi.testclient import TestClient

from career_sentinel import chat as chatmod, config, store
from career_sentinel.models import OfferDetail
from career_sentinel.web import app as webapp


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
    monkeypatch.setattr(webapp.pipeline, "build_pipeline",
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
