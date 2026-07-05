from fastapi.testclient import TestClient
from career_sentinel import store
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_track_with_match_json_stores_and_matched(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "a1", "company": "甲", "title": "後端",
                                     "match_score": 88, "match_json": {"score": 88, "reasons": ["r1"], "gaps": []}})
    assert r.json()["state"] == "matched"
    got = c.get("/api/tracked/a1").json()
    assert got["found"] is True and got["match"]["reasons"] == ["r1"] and got["tailor"] is None


def test_track_with_tailor_json_sets_tailored(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "a1", "tailor_json": {"cover_letter": "您好"}})
    assert r.json()["state"] == "tailored"
    got = c.get("/api/tracked/a1").json()
    assert got["tailor"]["cover_letter"] == "您好"


def test_get_tracked_not_found(tmp_path):
    got = _client(tmp_path).get("/api/tracked/nope").json()
    assert got["found"] is False and got["match"] is None and got["tailor"] is None


def test_track_json_preserved_across_calls(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "a1", "match_score": 80, "match_json": {"score": 80}})
    c.post("/api/tracked", json={"code": "a1", "tailor_json": {"cover_letter": "y"}})
    got = c.get("/api/tracked/a1").json()
    assert got["match"]["score"] == 80 and got["tailor"]["cover_letter"] == "y"


def test_sp16_behavior_unchanged_interested(tmp_path):
    # 無 json / 無 score → interested（SP16 行為回歸）
    c = _client(tmp_path)
    assert c.post("/api/tracked", json={"code": "a1", "title": "後端"}).json()["state"] == "interested"


def test_snapshot_has_tracked_codes(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "a1", "title": "後端"})
    c.post("/api/tracked", json={"code": "b2", "title": "前端"})
    body = c.get("/api/snapshot").json()
    assert set(body["tracked_codes"]) == {"a1", "b2"}


def test_snapshot_empty_tracked_codes(tmp_path):
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["tracked_codes"] == []
