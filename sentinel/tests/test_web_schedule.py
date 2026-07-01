from fastapi.testclient import TestClient

from career_sentinel.web import scheduler
from career_sentinel.web.app import create_app


def _client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def test_schedule_default_not_due(tmp_path):
    scheduler._reset_for_test()
    r = _client(tmp_path).get("/api/schedule")
    assert r.status_code == 200
    body = r.json()
    assert body["due"] is False
    assert set(body.keys()) == {"due", "notify_time", "last_prompted_date"}


def test_schedule_ack_clears_due(tmp_path):
    scheduler._reset_for_test()
    client = _client(tmp_path)
    scheduler._state.due = True
    assert client.get("/api/schedule").json()["due"] is True
    r = client.post("/api/schedule/ack")
    assert r.status_code == 200
    assert r.json()["due"] is False
    assert client.get("/api/schedule").json()["due"] is False


def test_status_exposes_change_counts(tmp_path):
    scheduler._reset_for_test()
    r = _client(tmp_path).get("/api/status")
    assert r.status_code == 200
    assert "last_change_counts" in r.json()
