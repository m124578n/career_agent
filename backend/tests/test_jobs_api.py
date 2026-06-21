import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import jobs as jobs_router
from job_tracker.db.repositories import (
    JobRepository,
    MatchRepository,
    QuotaRepository,
)
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


def _match(job_id: str, score: int) -> JobMatch:
    return JobMatch(
        job=make_job(job_id, f"c{job_id}"), score=score, reasons=["r"], gaps=["g"]
    )


def test_matches_endpoint_returns_sorted_for_user():
    db = AsyncMongoMockClient()["test"]
    match_repo = MatchRepository(db)
    asyncio.run(match_repo.set_match("dev@local", _match("1", 55)))
    asyncio.run(match_repo.set_match("dev@local", _match("2", 91)))

    app.dependency_overrides[deps.get_match_repo] = lambda: match_repo
    try:
        resp = TestClient(app).get("/api/jobs/matches")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert [m["score"] for m in body] == [91, 55]
    assert body[0]["job"]["job_id"] == "2"


def test_analyze_endpoint_delegates_and_counts_quota(monkeypatch):
    async def fake_analyze_jobs(user, keyword, target, job_repo, match_repo, **kwargs):
        assert user == "dev@local"
        assert keyword == "python"
        return [_match("9", 88), _match("8", 70)]

    monkeypatch.setattr(jobs_router, "analyze_jobs", fake_analyze_jobs)

    db = AsyncMongoMockClient()["test"]
    quota = QuotaRepository(db)
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: quota
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
    assert resp.json()[0]["score"] == 88
    # 以實際分析筆數計入額度（2 筆）
    assert asyncio.run(quota.used_today("dev@local")) == 2
