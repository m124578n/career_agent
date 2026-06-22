import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import jobs as jobs_router
from job_tracker.db.repositories import (
    JobRepository,
    MatchRepository,
    QuotaRepository,
    SearchRepository,
)
from job_tracker.main import app
from job_tracker.schemas import Job, JobMatch


def make_job(job_id: str, code: str) -> Job:
    return Job(job_id=job_id, code=code, title="工程師", company="某公司",
               url=f"https://www.104.com.tw/job/{code}")


def _match(job_id: str, score: int) -> JobMatch:
    return JobMatch(job=make_job(job_id, f"c{job_id}"), score=score,
                    reasons=["r"], gaps=["g"])


_PAYLOAD = {
    "keyword": "python",
    "target": {"target_title": "後端工程師", "expected_salary": 70000,
               "resume_text": "Python"},
}


def _wire(db, monkeypatch, fake):
    monkeypatch.setattr(jobs_router, "analyze_jobs", fake)
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)


def test_create_search_returns_id_and_matches(monkeypatch):
    db = AsyncMongoMockClient()["test"]

    async def fake(search_id, user, keyword, target, job_repo, match_repo, **kw):
        return [_match("9", 88), _match("8", 70)]

    _wire(db, monkeypatch, fake)
    try:
        resp = TestClient(app).post("/api/jobs/searches", json=_PAYLOAD)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["search_id"]
    assert body["matches"][0]["score"] == 88
    # 計入額度（2 筆）
    assert asyncio.run(QuotaRepository(db).used_today("dev@local")) == 2
    # search 已建立並推進 offset
    run = asyncio.run(SearchRepository(db).get(body["search_id"]))
    assert run.next_offset == 5
    assert run.count == 2


def test_list_and_get_search_matches(monkeypatch):
    db = AsyncMongoMockClient()["test"]

    async def fake(search_id, user, keyword, target, job_repo, match_repo, **kw):
        await match_repo.set_match(search_id, user, _match("9", 88))
        return [_match("9", 88)]

    _wire(db, monkeypatch, fake)
    try:
        client = TestClient(app)
        sid = client.post("/api/jobs/searches", json=_PAYLOAD).json()["search_id"]
        searches = client.get("/api/jobs/searches").json()
        matches = client.get(f"/api/jobs/searches/{sid}/matches").json()
    finally:
        app.dependency_overrides.clear()

    assert [s["search_id"] for s in searches] == [sid]
    assert matches[0]["job"]["job_id"] == "9"


def test_delete_search(monkeypatch):
    db = AsyncMongoMockClient()["test"]

    async def fake(search_id, user, keyword, target, job_repo, match_repo, **kw):
        return []

    _wire(db, monkeypatch, fake)
    try:
        client = TestClient(app)
        sid = client.post("/api/jobs/searches", json=_PAYLOAD).json()["search_id"]
        resp = client.delete(f"/api/jobs/searches/{sid}")
        searches = client.get("/api/jobs/searches").json()
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert searches == []
