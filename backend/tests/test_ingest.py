import json
from pathlib import Path

import httpx
from mongomock_motor import AsyncMongoMockClient

from job_tracker import crawler
from job_tracker.db.repositories import JobRepository
from job_tracker.services.ingest import ingest_jobs

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH = json.loads((FIXTURES / "104_search.json").read_text(encoding="utf-8"))
DETAIL = json.loads((FIXTURES / "104_detail.json").read_text(encoding="utf-8"))


def _handler(request: httpx.Request) -> httpx.Response:
    if "search/api/jobs" in str(request.url):
        return httpx.Response(200, json=SEARCH)
    return httpx.Response(200, json=DETAIL)


async def test_ingest_stores_jobs_and_details(monkeypatch):
    # 節流的 sleep 在測試中略過
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(crawler.asyncio, "sleep", no_sleep)

    repo = JobRepository(AsyncMongoMockClient()["test"])
    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        jobs = await ingest_jobs("python", repo, client=client)

    assert len(jobs) == 2
    stored = await repo.list_jobs()
    assert len(stored) == 2
    # 詳情有被抓並存入
    detail = await repo.get_detail(jobs[0].job_id)
    assert detail is not None
    assert detail.salary == "待遇面議"
