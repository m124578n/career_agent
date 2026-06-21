import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.db.repositories import JobRepository, QuotaRepository
from job_tracker.main import app
from job_tracker.schemas import Job
from job_tracker.services import cover_letter


def make_job(job_id: str = "1") -> Job:
    return Job(
        job_id=job_id,
        code="abc",
        title="Backend Engineer",
        company="某公司",
        url="https://www.104.com.tw/job/abc",
    )


def _body(job_id: str) -> dict:
    return {
        "target": {
            "target_title": "後端工程師",
            "expected_salary": 70000,
            "resume_text": "Python 經驗",
        },
        "job_id": job_id,
    }


def test_cover_letter_endpoint_returns_text(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    repo = JobRepository(db)
    asyncio.run(repo.upsert_job(make_job("1")))

    async def fake_generate(target, job, detail=None, *, client=None):
        assert job.job_id == "1"
        return "敬啟者，這是一封求職信。"

    monkeypatch.setattr(cover_letter, "generate", fake_generate)

    app.dependency_overrides[deps.get_job_repo] = lambda: repo
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    try:
        resp = TestClient(app).post("/api/applications/cover-letter", json=_body("1"))
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["cover_letter"].startswith("敬啟者")


def test_cover_letter_endpoint_404_for_missing_job():
    db = AsyncMongoMockClient()["test"]
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    try:
        resp = TestClient(app).post("/api/applications/cover-letter", json=_body("nope"))
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404
