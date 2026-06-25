import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.main import app
from job_tracker.schemas import Job


_PAYLOAD = {"keyword": "python",
            "target": {"target_title": "後端", "expected_salary": 70000, "resume_text": "Python"}}


@pytest.mark.asyncio
async def test_search_enqueues_search_task(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    from job_tracker.db.repositories import CrawlTaskRepository
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/jobs/searches", json=_PAYLOAD)
            body = resp.json()
    finally:
        app.dependency_overrides.clear()
    assert body["search_id"] and body["status"] == "queued"
    task = await CrawlTaskRepository(db).claim()
    assert task.type == "search" and task.payload["keyword"] == "python"


@pytest.mark.asyncio
async def test_analyze_enqueues_detail_tasks(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.db.repositories import CrawlTaskRepository
    from job_tracker.schemas import Job
    match_repo = MatchRepository(db)
    search_repo = SearchRepository(db)
    run = await search_repo.create("dev@local", "python",
                                   {"target_title": "後端", "expected_salary": 70000,
                                    "resume_text": "Python"})
    await match_repo.add_candidate(run.search_id, "dev@local",
                                   Job(job_id="1", code="abc", title="t", company="c",
                                       url="https://x/abc"), True)
    app.dependency_overrides[deps.get_match_repo] = lambda: match_repo
    app.dependency_overrides[deps.get_search_repo] = lambda: search_repo
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/jobs/searches/{run.search_id}/analyze",
                                     json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["queued"] == 1
    task = await CrawlTaskRepository(db).claim()
    assert task.type == "detail" and task.job_id == "1" and task.payload["code"] == "abc"
    assert (await match_repo.get_match(run.search_id, "1")).status == "pending"


@pytest.mark.asyncio
async def test_analyze_over_quota_is_429(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.db.repositories import CrawlTaskRepository
    match_repo = MatchRepository(db)
    search_repo = SearchRepository(db)
    run = await search_repo.create("dev@local", "python",
                                   {"target_title": "後端", "expected_salary": 70000,
                                    "resume_text": "Python"})
    await match_repo.add_candidate(run.search_id, "dev@local",
                                   Job(job_id="1", code="c1", title="t", company="co",
                                       url="https://x/c1"), True)
    await QuotaRepository(db).add("dev@local", 50)  # 已用滿（預設上限 50）
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: match_repo
    app.dependency_overrides[deps.get_search_repo] = lambda: search_repo
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/jobs/searches/{run.search_id}/analyze",
                                     json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_analyze_skips_already_done(monkeypatch):
    """已分析（done）的職缺重送不重跑、不重複計額度（後端正確性邊界）。"""
    db = AsyncMongoMockClient()["test"]
    from job_tracker.db.repositories import CrawlTaskRepository
    from job_tracker.schemas import JobMatch
    match_repo = MatchRepository(db)
    search_repo = SearchRepository(db)
    run = await search_repo.create("dev@local", "python",
                                   {"target_title": "後端", "expected_salary": 70000,
                                    "resume_text": "Python"})
    job = Job(job_id="1", code="c1", title="t", company="co", url="https://x/c1")
    await match_repo.add_candidate(run.search_id, "dev@local", job, True)
    # 模擬已完成分析
    await match_repo.set_result(run.search_id, "1",
                                JobMatch(job=job, score=88, reasons=["r"], gaps=["g"]))
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: match_repo
    app.dependency_overrides[deps.get_search_repo] = lambda: search_repo
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/jobs/searches/{run.search_id}/analyze",
                                     json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_analyze_allows_retry_failed(monkeypatch):
    """失敗（failed）的職缺可重試（重新分析）。"""
    db = AsyncMongoMockClient()["test"]
    from job_tracker.db.repositories import CrawlTaskRepository
    match_repo = MatchRepository(db)
    search_repo = SearchRepository(db)
    run = await search_repo.create("dev@local", "python",
                                   {"target_title": "後端", "expected_salary": 70000,
                                    "resume_text": "Python"})
    await match_repo.add_candidate(run.search_id, "dev@local",
                                   Job(job_id="1", code="c1", title="t", company="co",
                                       url="https://x/c1"), True)
    await match_repo.set_failed(run.search_id, "1")  # 模擬前次分析失敗
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: match_repo
    app.dependency_overrides[deps.get_search_repo] = lambda: search_repo
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/jobs/searches/{run.search_id}/analyze",
                                     json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["queued"] == 1
    task = await CrawlTaskRepository(db).claim()
    assert task.type == "detail" and task.job_id == "1"
    assert (await match_repo.get_match(run.search_id, "1")).status == "pending"


@pytest.mark.asyncio
async def test_get_single_search_returns_crawl_status(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    search_repo = SearchRepository(db)
    run = await search_repo.create("dev@local", "python",
                                   {"target_title": "後端", "expected_salary": None,
                                    "resume_text": "x"})
    app.dependency_overrides[deps.get_search_repo] = lambda: search_repo
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/jobs/searches/{run.search_id}")
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["crawl_status"] == "queued"


@pytest.mark.asyncio
async def test_agent_status_endpoint(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.db.repositories import AgentStatusRepository, CrawlTaskRepository
    app.dependency_overrides[deps.get_agent_status_repo] = lambda: AgentStatusRepository(db)
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/jobs/agent-status")
    finally:
        app.dependency_overrides.clear()
    body = resp.json()
    assert body["online"] is False and body["pending"] == 0
