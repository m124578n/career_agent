from fastapi.testclient import TestClient

from career_sentinel import store
from career_sentinel.web.app import create_app


def test_stats_endpoint_shape(tmp_path):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    store.merge_tracked_job(conn, "a", state="interested", company="甲", title="後端")
    store.set_tracked_state(conn, "b", "offer")
    c = TestClient(create_app(db_path=db))
    r = c.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert {"funnel", "rejected_count", "conversions", "dwell", "stale"} <= set(body)
    assert body["funnel"][0]["state"] == "interested"
    assert isinstance(body["conversions"]["interested_to_offer"], int)


def test_stats_endpoint_empty(tmp_path):
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    c = TestClient(create_app(db_path=db))
    r = c.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["rejected_count"] == 0 and body["stale"] == []
    assert body["conversions"]["applied_to_interview"] is None
