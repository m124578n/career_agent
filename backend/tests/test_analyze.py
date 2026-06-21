import json
from pathlib import Path

import httpx
from mongomock_motor import AsyncMongoMockClient

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


def _no_throttle(monkeypatch):
    async def no_sleep(_s):
        return None

    monkeypatch.setattr(analyze_mod.asyncio, "sleep", no_sleep)


async def test_analyze_jobs_stores_and_sorts(monkeypatch):
    _no_throttle(monkeypatch)
    scores = iter([50, 80])

    async def fake_analyze(target, job, detail, *, client=None):
        return JobMatch(job=job, score=next(scores), reasons=["r"], gaps=["g"])

    monkeypatch.setattr(analyze_mod.job_matching, "analyze", fake_analyze)

    repo = JobRepository(AsyncMongoMockClient()["test"])
    target = ResumeTarget(target_title="X", resume_text="Y")
    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        matches = await analyze_jobs("python", target, repo, http_client=http_client)

    assert [m.score for m in matches] == [80, 50]
    stored = await repo.list_matches()
    assert [m.score for m in stored] == [80, 50]


async def test_analyze_jobs_skips_failed(monkeypatch):
    _no_throttle(monkeypatch)
    calls = {"n": 0}

    async def flaky_analyze(target, job, detail, *, client=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("LLM 暫時失敗")
        return JobMatch(job=job, score=70, reasons=[], gaps=[])

    monkeypatch.setattr(analyze_mod.job_matching, "analyze", flaky_analyze)

    repo = JobRepository(AsyncMongoMockClient()["test"])
    target = ResumeTarget(target_title="X", resume_text="Y")
    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        matches = await analyze_jobs("python", target, repo, http_client=http_client)

    # 第一筆失敗被跳過，仍回傳第二筆
    assert len(matches) == 1
    assert matches[0].score == 70


# 保留 job_matching 參考供匯入檢查
_ = job_matching
