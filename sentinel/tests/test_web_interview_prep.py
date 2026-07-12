from fastapi.testclient import TestClient

from career_sentinel import interview_prep as ip_mod, jobfetch, store
from career_sentinel.models import InterviewPrep, JobDetail
from career_sentinel.web.app import create_app


def _seed_resume(conn):
    st = store.load_resume(conn)
    st.resume_text = "我有三年後端經驗"
    store.save_resume(conn, st)


def test_interview_prep_endpoint_ok(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    _seed_resume(conn)
    store.merge_tracked_job(conn, "abc12", state="interested", company="甲", title="後端")
    monkeypatch.setattr(jobfetch, "fetch_job_detail", lambda code, **kw: JobDetail(title="後端", company="甲"))
    monkeypatch.setattr(ip_mod, "prepare_interview",
                        lambda jd, resume, gaps, title, **kw: InterviewPrep(likely_questions=["Q1"], deep=kw.get("deep", False)))
    c = TestClient(create_app(db_path=db))
    r = c.post("/api/tracked/abc12/interview-prep", json={"deep": False})
    assert r.status_code == 200
    assert r.json()["likely_questions"] == ["Q1"]
    # 已存檔：GET 帶出
    g = c.get("/api/tracked/abc12").json()
    assert g["interview_prep"]["likely_questions"] == ["Q1"]


def test_interview_prep_requires_resume(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    c = TestClient(create_app(db_path=db))
    r = c.post("/api/tracked/abc12/interview-prep", json={"deep": False})
    assert r.status_code == 400 and "履歷" in r.json()["detail"]
