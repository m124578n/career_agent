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


def test_snapshot_exposes_interviews_with_gcal_link(tmp_path):
    from fastapi.testclient import TestClient
    from career_sentinel import store
    from career_sentinel.models import Interview, Snapshot
    from career_sentinel.web.app import create_app
    db = str(tmp_path / "t.db")
    conn = store.connect(db)
    store.save_snapshot(conn, Snapshot(interviews=[
        Interview(company="乙公司", job_title="PM", when="2026-04-09 13:30:00", location="新竹", job_url="u2"),
        Interview(company="甲公司", job_title="後端", when="2026-04-07 10:00:00", location="台北", job_url="u1"),
    ]), run_at="2026-07-02T09:00:00")
    client = TestClient(create_app(db_path=db))
    r = client.get("/api/snapshot")
    assert r.status_code == 200
    ivs = r.json()["interviews"]
    assert len(ivs) == 2
    assert ivs[0]["when"] == "2026-04-07 10:00:00"  # 按 when 升冪，早的在前
    assert ivs[0]["company"] == "甲公司"
    assert "calendar.google.com" in ivs[0]["gcal_link"]
    assert "dates=" in ivs[0]["gcal_link"]


def test_interview_dismiss_and_restore(tmp_path):
    from career_sentinel.models import Interview, Snapshot, interview_key
    conn = store.connect(tmp_path / "db.sqlite")
    iv = Interview(company="甲", job_title="後端", when="2026-04-07 10:00:00")
    store.save_snapshot(conn, Snapshot(interviews=[iv]), run_at="2026-07-03T09:00:00")
    c = _client(tmp_path)
    body = c.get("/api/snapshot").json()
    assert body["interviews"][0]["key"] == interview_key(iv)
    assert body["interviews"][0]["dismissed"] is False
    assert c.post("/api/interviews/dismiss", json={"key": interview_key(iv)}).json() == {"ok": True}
    assert c.get("/api/snapshot").json()["interviews"][0]["dismissed"] is True
    c.post("/api/interviews/dismiss", json={"key": interview_key(iv)})  # 重複 dismiss 不重複記
    assert c.post("/api/interviews/restore", json={"key": interview_key(iv)}).json() == {"ok": True}
    assert c.get("/api/snapshot").json()["interviews"][0]["dismissed"] is False


def test_snapshot_exposes_company_url_from_raw(tmp_path):
    from career_sentinel.models import Application, Snapshot, Viewer
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        viewers=[Viewer(company="甲", job_title="後端", viewed_at="2026-07-01", raw={"custNo": "1a2x6b"})],
        applications=[Application(job_id="1", company="乙", title="PM", status="已讀", applied_at="",
                                  raw={"custUrl": "//www.104.com.tw/company/auxx12g"})],
    ), run_at="2026-07-03T09:00:00")
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["viewers"][0]["company_url"] == "https://www.104.com.tw/company/1a2x6b"
    assert body["applications"][0]["company_url"] == "https://www.104.com.tw/company/auxx12g"


def test_snapshot_exposes_thread_and_job_urls(tmp_path):
    from career_sentinel.models import Application, Interview, Message, Snapshot
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        applications=[Application(job_id="1", company="乙", title="PM", status="已讀", applied_at="",
                                  raw={"jobUrl": "//www.104.com.tw/job/8jet3"})],
        messages=[Message(thread_id="8wtoc", company="丙", last_message="hi", raw={"chatroomId": "8wtoc"})],
        interviews=[Interview(company="甲", job_title="後端", when="2026-04-07 10:00:00",
                              raw={"chatroomId": "8lwq3"})],
    ), run_at="2026-07-03T09:00:00")
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["applications"][0]["job_url"] == "https://www.104.com.tw/job/8jet3"
    assert body["messages"][0]["thread_url"] == "https://pda.104.com.tw/work/message/chat?chatroomId=8wtoc"
    assert body["interviews"][0]["thread_url"] == "https://pda.104.com.tw/work/message/chat?chatroomId=8lwq3"
