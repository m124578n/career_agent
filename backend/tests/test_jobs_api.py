import asyncio

import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import jobs as jobs_router
from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.main import app
from job_tracker.schemas import Job


class SyncRunner:
    """測試用：直接 await 所有 coros（在同一 event loop 內同步跑完）。"""
    async def _run(self, coros):
        for c in coros:
            await c

    def submit(self, coros):
        # 排程到 running loop，存 task 讓 drain 等待
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run(coros))


_PAYLOAD = {"keyword": "python",
            "target": {"target_title": "後端", "expected_salary": 70000, "resume_text": "Python"}}

_runner_instance: SyncRunner | None = None


def _wire(db, monkeypatch, candidates):
    global _runner_instance

    async def fake_crawl(search_id, user, keyword, area, page, job_repo, match_repo, **kw):
        for jid, rel in candidates:
            job = Job(job_id=jid, code=f"c{jid}", title="t", company="co", url=f"https://x/c{jid}")
            await match_repo.add_candidate(search_id, user, job, rel)
        return [await match_repo.get_match(search_id, jid) for jid, _ in candidates]

    async def fake_analyze_one(search_id, user, job_id, target, job_repo, match_repo, quota, **kw):
        from job_tracker.schemas import JobMatch
        m = await match_repo.get_match(search_id, job_id)
        await match_repo.set_result(search_id, job_id,
                                    JobMatch(job=m.job, score=88, reasons=["r"], gaps=["g"]))
        await quota.add(user, 1)

    _runner_instance = SyncRunner()
    monkeypatch.setattr(jobs_router, "crawl_candidates", fake_crawl)
    monkeypatch.setattr(jobs_router, "analyze_one", fake_analyze_one)
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    app.dependency_overrides[deps.get_analysis_runner] = lambda: _runner_instance


@pytest.mark.asyncio
async def test_search_returns_candidates(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True), ("2", False)])
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/jobs/searches", json=_PAYLOAD)
            body = resp.json()
    finally:
        app.dependency_overrides.clear()
    assert body["search_id"]
    assert [(c["job"]["job_id"], c["relevant"]) for c in body["candidates"]] == [("1", True), ("2", False)]
    assert await QuotaRepository(db).used_today("dev@local") == 0  # 不計額度


@pytest.mark.asyncio
async def test_analyze_selected_runs_and_counts_quota(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True), ("2", True)])
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            sid = (await client.post("/api/jobs/searches", json=_PAYLOAD)).json()["search_id"]
            resp = await client.post(f"/api/jobs/searches/{sid}/analyze", json={"job_ids": ["1"]})
            # 等待 runner 的背景 task 完成
            if _runner_instance and hasattr(_runner_instance, '_task'):
                await _runner_instance._task
            matches = (await client.get(f"/api/jobs/searches/{sid}/matches")).json()
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["queued"] == 1
    done = [m for m in matches if m["status"] == "done"]
    assert [m["job"]["job_id"] for m in done] == ["1"] and done[0]["score"] == 88
    assert await QuotaRepository(db).used_today("dev@local") == 1


@pytest.mark.asyncio
async def test_analyze_over_quota_is_429(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True)])
    await QuotaRepository(db).add("dev@local", 50)  # 已用滿（預設上限 50）
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            sid = (await client.post("/api/jobs/searches", json=_PAYLOAD)).json()["search_id"]
            resp = await client.post(f"/api/jobs/searches/{sid}/analyze", json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_analyze_skips_already_done(monkeypatch):
    """已分析（done）的職缺重送不重跑、不重複計額度（後端正確性邊界）。"""
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True)])
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            sid = (await client.post("/api/jobs/searches", json=_PAYLOAD)).json()["search_id"]
            await client.post(f"/api/jobs/searches/{sid}/analyze", json={"job_ids": ["1"]})
            if _runner_instance and hasattr(_runner_instance, "_task"):
                await _runner_instance._task
            # 再送同一個已 done 的 id → 非候選 → 400，不重跑
            resp2 = await client.post(f"/api/jobs/searches/{sid}/analyze", json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp2.status_code == 400
    assert await QuotaRepository(db).used_today("dev@local") == 1  # 沒重複計額度


@pytest.mark.asyncio
async def test_analyze_allows_retry_failed(monkeypatch):
    """失敗（failed）的職缺可重試（重新分析）。"""
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True)])
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            sid = (await client.post("/api/jobs/searches", json=_PAYLOAD)).json()["search_id"]
            await MatchRepository(db).set_failed(sid, "1")  # 模擬前次分析失敗
            resp = await client.post(f"/api/jobs/searches/{sid}/analyze", json={"job_ids": ["1"]})
            if _runner_instance and hasattr(_runner_instance, "_task"):
                await _runner_instance._task
            matches = (await client.get(f"/api/jobs/searches/{sid}/matches")).json()
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["queued"] == 1  # failed 可重試
    assert [m for m in matches if m["status"] == "done"][0]["job"]["job_id"] == "1"
