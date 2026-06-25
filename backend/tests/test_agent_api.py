import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.config import get_settings
from job_tracker.main import app


@pytest.fixture
def _secret(monkeypatch):
    monkeypatch.setenv("AGENT_SECRET", "s3cr3t")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_claim_rejects_wrong_secret(_secret):
    db = AsyncMongoMockClient()["test"]
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: deps.CrawlTaskRepository(db)
    app.dependency_overrides[deps.get_agent_status_repo] = lambda: deps.AgentStatusRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/claim", headers={"Authorization": "Bearer wrong"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401


def _wire(db):
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: deps.CrawlTaskRepository(db)
    app.dependency_overrides[deps.get_agent_status_repo] = lambda: deps.AgentStatusRepository(db)


@pytest.mark.asyncio
async def test_claim_returns_pending_task_with_secret(_secret):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.schemas import CrawlTask
    await deps.CrawlTaskRepository(db).enqueue(
        CrawlTask(task_id="t1", type="search",
                  payload={"keyword": "ai", "page": 1, "area": None},
                  search_id="s1", user="u@x"))
    _wire(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/claim", headers={"Authorization": "Bearer s3cr3t"})
    finally:
        app.dependency_overrides.clear()
    body = resp.json()
    assert resp.status_code == 200
    assert body["task"]["task_id"] == "t1"


@pytest.mark.asyncio
async def test_complete_marks_done(_secret):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.schemas import CrawlTask
    repo = deps.CrawlTaskRepository(db)
    await repo.enqueue(CrawlTask(task_id="t1", type="search",
                                 payload={"keyword": "ai", "page": 1, "area": None},
                                 search_id="s1", user="u@x"))
    await repo.claim()
    _wire(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/complete",
                                     headers={"Authorization": "Bearer s3cr3t"},
                                     json={"task_id": "t1", "raw_json": {"data": []}})
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["status"] == "done"
    assert (await repo.get("t1")).status == "done"


@pytest.mark.asyncio
async def test_complete_search_task_stores_candidates(_secret):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.schemas import CrawlTask
    repo = deps.CrawlTaskRepository(db)
    await repo.enqueue(CrawlTask(task_id="t1", type="search",
                                 payload={"keyword": "python", "page": 1, "area": None},
                                 search_id="s1", user="u@x"))
    await repo.claim()
    _wire(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: deps.MatchRepository(db)
    app.dependency_overrides[deps.get_job_repo] = lambda: deps.JobRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: deps.SearchRepository(db)
    raw = {"data": [{"jobNo": "1", "jobName": "Python", "custName": "A",
                     "link": {"job": "https://www.104.com.tw/job/abc"},
                     "descSnippet": "[[[Python]]]", "salaryLow": 0, "salaryHigh": 0}]}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/agent/complete",
                              headers={"Authorization": "Bearer s3cr3t"},
                              json={"task_id": "t1", "raw_json": raw})
    finally:
        app.dependency_overrides.clear()
    cands = await deps.MatchRepository(db).list_by_search("s1")
    assert [c.job.job_id for c in cands] == ["1"]
