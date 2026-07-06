from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel import store
from career_sentinel.models import JobDetail, MatchResult, ResumeState


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_match_invalid_url_400(tmp_path):
    r = _client(tmp_path).post("/api/match", json={"job_url": "https://example.com/x"})
    assert r.status_code == 400


def test_match_no_resume_400(tmp_path):
    r = _client(tmp_path).post("/api/match", json={"job_url": "https://www.104.com.tw/job/8pu2t"})
    assert r.status_code == 400  # 履歷為空（在抓取前擋下）


def test_match_success(tmp_path, monkeypatch):
    from career_sentinel import jobfetch, match
    monkeypatch.setattr(jobfetch, "fetch_job_detail", lambda code, **kw: JobDetail(title="全端工程師", company="範例", salary="月薪 6 萬", description="Python"))
    monkeypatch.setattr(match, "match", lambda rt, tt, jd, **kw: MatchResult(score=80, reasons=["熟 Python"], gaps=["缺雲端"]))
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_resume(conn, ResumeState(resume_text="我會 Python"))
    c = _client(tmp_path)
    r = c.post("/api/match", json={"job_url": "https://www.104.com.tw/job/8pu2t"})
    assert r.status_code == 200
    b = r.json()
    assert b["title"] == "全端工程師"
    assert b["company"] == "範例"
    assert b["score"] == 80
    assert b["gaps"] == ["缺雲端"]
