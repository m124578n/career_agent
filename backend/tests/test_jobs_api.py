import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api.routers import jobs as jobs_router
from job_tracker.api.routers.jobs import get_repo
from job_tracker.db.repositories import JobRepository
from job_tracker.main import app
from job_tracker.schemas import Job, JobMatch


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


def _match(job_id: str, score: int) -> JobMatch:
    return JobMatch(
        job=make_job(job_id, f"c{job_id}"), score=score, reasons=["r"], gaps=["g"]
    )


def test_matches_endpoint_returns_sorted():
    repo = JobRepository(AsyncMongoMockClient()["test"])
    asyncio.run(repo.upsert_job(make_job("1", "c1")))
    asyncio.run(repo.upsert_job(make_job("2", "c2")))
    asyncio.run(repo.set_match("1", _match("1", 55)))
    asyncio.run(repo.set_match("2", _match("2", 91)))

    app.dependency_overrides[get_repo] = lambda: repo
    try:
        resp = TestClient(app).get("/api/jobs/matches")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert [m["score"] for m in body] == [91, 55]
    assert body[0]["job"]["job_id"] == "2"


def test_analyze_endpoint_delegates(monkeypatch):
    async def fake_analyze_jobs(keyword, target, repo, **kwargs):
        assert keyword == "python"
        return [_match("9", 88)]

    monkeypatch.setattr(jobs_router, "analyze_jobs", fake_analyze_jobs)

    repo = JobRepository(AsyncMongoMockClient()["test"])
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        resp = TestClient(app).post(
            "/api/jobs/analyze",
            json={
                "keyword": "python",
                "target": {
                    "target_title": "後端工程師",
                    "expected_salary": 70000,
                    "resume_text": "Python",
                },
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["score"] == 88
