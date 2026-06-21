import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api.routers.jobs import get_repo
from job_tracker.db.repositories import JobRepository
from job_tracker.main import app
from job_tracker.schemas import Job


def make_job(job_id: str, code: str) -> Job:
    return Job(
        job_id=job_id,
        code=code,
        title="工程師",
        company="某公司",
        url=f"https://www.104.com.tw/job/{code}",
    )


def test_list_jobs_returns_stored_jobs():
    repo = JobRepository(AsyncMongoMockClient()["test"])
    asyncio.run(repo.upsert_job(make_job("1", "aaa")))
    asyncio.run(repo.upsert_job(make_job("2", "bbb")))

    app.dependency_overrides[get_repo] = lambda: repo
    try:
        resp = TestClient(app).get("/api/jobs")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert {j["job_id"] for j in body} == {"1", "2"}
