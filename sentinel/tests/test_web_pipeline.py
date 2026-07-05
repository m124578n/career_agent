from fastapi.testclient import TestClient

from career_sentinel import store
from career_sentinel.web import app as webapp
from career_sentinel.models import Application, Interview, Snapshot


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_snapshot_empty_has_pipeline_key(tmp_path):
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["pipeline"] == []
    # 既有欄位保留
    assert body["applications"] == [] and body["interviews"] == []


def test_snapshot_pipeline_from_scrape(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        applications=[Application(job_id="a1", company="甲", title="後端", status="已讀", applied_at="2026-07-01")],
        interviews=[Interview(company="乙", job_title="前端", when="2026-07-10 14:00:00",
                              location="台北", job_url="https://www.104.com.tw/job/bb2cc")],
    ), run_at="2026-07-05T10:00:00")
    body = _client(tmp_path).get("/api/snapshot").json()
    states = {j["code"]: j["state"] for j in body["pipeline"]}
    assert states["a1"] == "applied"
    assert states["bb2cc"] == "interviewing"


def test_snapshot_survives_pipeline_error(tmp_path, monkeypatch):
    # build_pipeline 丟例外時，snapshot 其他欄位仍完整、pipeline 回 []
    from career_sentinel import pipeline
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        applications=[Application(job_id="a1", company="甲", title="後端", status="已讀", applied_at="2026-07-01")],
    ), run_at="2026-07-05T10:00:00")
    monkeypatch.setattr(pipeline, "build_pipeline", lambda c: (_ for _ in ()).throw(RuntimeError("boom")))
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["pipeline"] == []
    assert body["applications"][0]["job_id"] == "a1"  # 其他欄位不受影響
