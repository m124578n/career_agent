from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel.web import runner
from career_sentinel import store
from career_sentinel.models import Application, Message, Snapshot, Viewer


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_snapshot_empty(tmp_path):
    r = _client(tmp_path).get("/api/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["run_at"] is None
    assert body["viewers"] == [] and body["applications"] == [] and body["messages"] == []
    assert "尚無資料" in body["digest"]


def test_snapshot_returns_stored(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        viewers=[Viewer(company="台積電", job_title="後端", viewed_at="2026-06-28")],
        applications=[Application(job_id="1", company="台積電", title="後端", status="已讀", applied_at="2026-06-20")],
        messages=[Message(thread_id="t1", company="台積電", last_message="想約面試", has_interview_invite=True)],
    ), run_at="2026-06-28T10:00:00")
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["run_at"] == "2026-06-28T10:00:00"
    assert body["viewers"][0]["company"] == "台積電"
    assert body["applications"][0]["status"] == "已讀"
    assert body["messages"][0]["has_interview_invite"] is True
    assert "台積電" in body["digest"]


def test_scrape_starts_and_rejects_concurrent(tmp_path, monkeypatch):
    calls = {"n": 0}
    def fake_start(launch):
        calls["n"] += 1
        return calls["n"] == 1  # 第一次 True、第二次 False
    monkeypatch.setattr(runner, "start_scrape", fake_start)
    c = _client(tmp_path)
    assert c.post("/api/scrape").json() == {"status": "running"}
    r2 = c.post("/api/scrape")
    assert r2.status_code == 409
    assert r2.json() == {"status": "already_running"}


def test_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "status", lambda: {"running": False, "last_run": "2026-06-28T10:00:00", "last_error": None, "last_failed_readers": []})
    body = _client(tmp_path).get("/api/status").json()
    assert body["running"] is False
    assert body["last_run"] == "2026-06-28T10:00:00"
