from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel.models import ResumeDiagnosis


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_resume_get_default(tmp_path):
    body = _client(tmp_path).get("/api/resume").json()
    assert body["has_resume"] is False
    assert body["chars"] == 0
    assert body["diagnosis"] is None


def test_resume_upload_txt(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/resume/upload", files={"file": ("r.txt", "我的履歷後端".encode("utf-8"), "text/plain")})
    assert r.status_code == 200
    assert r.json()["chars"] == len("我的履歷後端")
    assert c.get("/api/resume").json()["has_resume"] is True


def test_resume_diagnose_no_resume_400(tmp_path):
    r = _client(tmp_path).post("/api/resume/diagnose")
    assert r.status_code == 400


def test_resume_diagnose_success(tmp_path, monkeypatch):
    from career_sentinel import diagnosis
    monkeypatch.setattr(diagnosis, "diagnose", lambda text, title, sal, **kw: ResumeDiagnosis(strengths=["A"], gaps=["B"]))
    c = _client(tmp_path)
    c.post("/api/resume/upload", files={"file": ("r.txt", "履歷".encode("utf-8"), "text/plain")})
    c.put("/api/preferences", json={"target_title": "後端工程師", "expected_salary": 60000,
                                    "locations": [], "conditions": [], "avoid": []})
    r = c.post("/api/resume/diagnose")
    assert r.status_code == 200
    assert r.json()["strengths"] == ["A"]
    assert c.get("/api/resume").json()["diagnosis"]["gaps"] == ["B"]
    assert c.get("/api/preferences").json()["target_title"] == "後端工程師"
