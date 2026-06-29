from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel import store
from career_sentinel.models import Snapshot, Viewer


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_get_settings_default(tmp_path):
    body = _client(tmp_path).get("/api/settings").json()
    assert body["watched_companies"] == []
    assert body["watched_keywords"] == []
    assert body["notify_time"] is None


def test_put_and_get_settings_roundtrip(tmp_path):
    c = _client(tmp_path)
    r = c.put("/api/settings", json={"watched_companies": ["台積電"], "watched_keywords": ["後端"], "notify_time": "09:30"})
    assert r.status_code == 200
    body = c.get("/api/settings").json()
    assert body["watched_companies"] == ["台積電"]
    assert body["notify_time"] == "09:30"


def test_put_settings_invalid_time_422(tmp_path):
    r = _client(tmp_path).put("/api/settings", json={"watched_companies": [], "watched_keywords": [], "notify_time": "25:99"})
    assert r.status_code == 422


def test_snapshot_includes_watched_flag(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        viewers=[Viewer(company="台積電股份有限公司", job_title="後端", viewed_at="t")],
    ), run_at="2026-06-29T10:00:00")
    c = _client(tmp_path)
    c.put("/api/settings", json={"watched_companies": ["台積電"], "watched_keywords": [], "notify_time": None})
    body = c.get("/api/snapshot").json()
    assert body["viewers"][0]["watched"] is True
