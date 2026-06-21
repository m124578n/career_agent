from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import resumes
from job_tracker.db.repositories import QuotaRepository
from job_tracker.main import app
from job_tracker.schemas import ResumeDiagnosis


def test_diagnose_endpoint_returns_diagnosis(monkeypatch):
    async def fake_diagnose(target, **kwargs):
        return ResumeDiagnosis(strengths=["優勢A"], gaps=["缺口B"])

    monkeypatch.setattr(resumes.resume_diagnosis, "diagnose", fake_diagnose)

    quota = QuotaRepository(AsyncMongoMockClient()["test"])
    app.dependency_overrides[deps.get_quota_repo] = lambda: quota
    try:
        resp = TestClient(app).post(
            "/api/resumes/diagnose",
            json={
                "target_title": "後端工程師",
                "expected_salary": 70000,
                "resume_text": "Python 經驗",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["strengths"] == ["優勢A"]
    assert body["gaps"] == ["缺口B"]
