from fastapi.testclient import TestClient

from career_sentinel import store
from career_sentinel.web import app as webapp
from career_sentinel.models import TrackedJob


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_track_with_score_sets_matched(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端",
                                     "url": "https://www.104.com.tw/job/abc12", "salary": "6萬", "match_score": 82})
    assert r.status_code == 200
    assert r.json() == {"status": "tracked", "state": "matched"}
    conn = store.connect(tmp_path / "db.sqlite")
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1 and jobs[0].code == "abc12" and jobs[0].state == "matched" and jobs[0].match_score == 82


def test_track_without_score_sets_interested(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端"})
    assert r.json()["state"] == "interested"


def test_track_empty_code_400(tmp_path):
    r = _client(tmp_path).post("/api/tracked", json={"code": "  "})
    assert r.status_code == 400


def test_retrack_same_code_upserts_keeps_created_at(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端"})  # interested
    conn = store.connect(tmp_path / "db.sqlite")
    created0 = store.get_tracked_job(conn, "abc12").created_at
    c.post("/api/tracked", json={"code": "abc12", "match_score": 90})  # → matched
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1  # upsert，不新增
    j = store.get_tracked_job(conn, "abc12")
    assert j.state == "matched" and j.match_score == 90
    assert j.created_at == created0  # created_at 保留
    assert j.company == "甲"  # 舊值在新請求未帶時保留


def test_retrack_does_not_downgrade_terminal(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="offer", created_at="2026-07-01T00:00:00"))
    _client(tmp_path).post("/api/tracked", json={"code": "abc12", "match_score": 70})
    assert store.get_tracked_job(conn, "abc12").state == "offer"  # 不降級


def test_retrack_keeps_furthest_state(tmp_path):
    # 已 matched，再用「無分數（interested）」追蹤 → 維持 matched（取較前面）
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="matched", match_score=80, created_at="2026-07-01T00:00:00"))
    _client(tmp_path).post("/api/tracked", json={"code": "abc12"})
    assert store.get_tracked_job(conn, "abc12").state == "matched"


def test_untrack_removes(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "abc12", "title": "後端"})
    r = c.delete("/api/tracked/abc12")
    assert r.json() == {"status": "untracked"}
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_tracked_jobs(conn) == []


def test_untrack_missing_code_ok(tmp_path):
    r = _client(tmp_path).delete("/api/tracked/nope")
    assert r.status_code == 200  # 不存在也不報錯


def test_get_job_by_url(tmp_path, monkeypatch):
    from career_sentinel import jobfetch
    from career_sentinel.models import JobDetail
    monkeypatch.setattr(jobfetch, "fetch_job_detail",
                        lambda code, **kw: JobDetail(title="後端工程師", company="甲公司", salary="月薪6萬"))
    r = _client(tmp_path).get("/api/job", params={"url": "https://www.104.com.tw/job/abc12"})
    assert r.status_code == 200
    b = r.json()
    assert b["code"] == "abc12" and b["title"] == "後端工程師" and b["company"] == "甲公司" and b["salary"] == "月薪6萬"


def test_get_job_bad_url_400(tmp_path):
    r = _client(tmp_path).get("/api/job", params={"url": "https://example.com/x"})
    assert r.status_code == 400


def test_track_then_snapshot_pipeline_has_matched(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端", "match_score": 75})
    body = c.get("/api/snapshot").json()
    states = {j["code"]: j["state"] for j in body["pipeline"]}
    assert states.get("abc12") == "matched"
