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


def test_match_tracks_job_as_matched(tmp_path, monkeypatch):
    # 按比對即代表這筆進入管道「已比對」——後端自動追蹤，不需前端另外按追蹤。
    from career_sentinel import jobfetch, match
    monkeypatch.setattr(jobfetch, "fetch_job_detail", lambda code, **kw: JobDetail(title="全端工程師", company="範例", salary="月薪 6 萬", description="Python"))
    monkeypatch.setattr(match, "match", lambda rt, tt, jd, **kw: MatchResult(score=80, reasons=["熟 Python"], gaps=["缺雲端"]))
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_resume(conn, ResumeState(resume_text="我會 Python"))
    c = _client(tmp_path)
    r = c.post("/api/match", json={"job_url": "https://www.104.com.tw/job/8pu2t"})
    assert r.status_code == 200
    tj = store.get_tracked_job(conn, "8pu2t")
    assert tj is not None
    assert tj.state == "matched"
    assert tj.match_score == 80
    assert tj.company == "範例"


def test_tailor_tracks_job_as_tailored(tmp_path, monkeypatch):
    # 客製化即代表這筆進入管道「已客製化」——後端自動追蹤（聊天/職缺卡皆然）。
    from career_sentinel import jobfetch, tailor
    from career_sentinel.models import TailoredApplication
    monkeypatch.setattr(jobfetch, "fetch_job_detail", lambda code, **kw: JobDetail(title="後端工程師", company="甲公司", salary="月薪 7 萬"))
    monkeypatch.setattr(tailor, "tailor_application", lambda rt, tt, jd, **kw: TailoredApplication(job_title=jd.title, company=jd.company, resume_tips=["強調 Python"], cover_letter="敬啟者…"))
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_resume(conn, ResumeState(resume_text="Python 五年"))
    c = _client(tmp_path)
    r = c.post("/api/tailor", json={"job_url": "https://www.104.com.tw/job/8pu2t"})
    assert r.status_code == 200
    tj = store.get_tracked_job(conn, "8pu2t")
    assert tj is not None
    assert tj.state == "tailored"
    assert tj.tailor_json  # 已存客製化結果
