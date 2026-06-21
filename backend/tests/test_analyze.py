import json
from pathlib import Path

import httpx
from mongomock_motor import AsyncMongoMockClient

from job_tracker import crawler
from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import JobMatch, ResumeTarget
from job_tracker.services import analyze as analyze_mod
from job_tracker.services import job_matching
from job_tracker.services.analyze import analyze_jobs

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH = json.loads((FIXTURES / "104_search.json").read_text(encoding="utf-8"))
DETAIL = json.loads((FIXTURES / "104_detail.json").read_text(encoding="utf-8"))


def _handler(request: httpx.Request) -> httpx.Response:
    if "search/api/jobs" in str(request.url):
        return httpx.Response(200, json=SEARCH)
    return httpx.Response(200, json=DETAIL)


async def test_analyze_jobs_stores_and_sorts(monkeypatch):
    async def no_sleep(_s):
        return None

    monkeypatch.setattr(crawler.asyncio, "sleep", no_sleep)

    scores = iter([50, 80])

    async def fake_analyze(target, job, detail, *, client=None):
        return JobMatch(job=job, score=next(scores), reasons=["r"], gaps=["g"])

    monkeypatch.setattr(job_matching, "analyze", fake_analyze)
    # analyze_jobs 透過 job_matching 模組呼叫，確保 patch 對到同一個參考
    monkeypatch.setattr(analyze_mod.job_matching, "analyze", fake_analyze)

    repo = JobRepository(AsyncMongoMockClient()["test"])
    target = ResumeTarget(target_title="X", resume_text="Y")
    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        matches = await analyze_jobs("python", target, repo, http_client=http_client)

    # 回傳依分數由高到低
    assert [m.score for m in matches] == [80, 50]
    # 已落 DB：list_matches 也排序
    stored = await repo.list_matches()
    assert [m.score for m in stored] == [80, 50]
