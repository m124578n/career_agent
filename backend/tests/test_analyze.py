import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.schemas import Job, JobMatch, ResumeTarget
from job_tracker.services import analyze as analyze_svc


def _target():
    return ResumeTarget(target_title="後端", resume_text="Python")


def _search_resp():
    return httpx.Response(200, json={"data": [
        {"jobNo": "1", "jobName": "Python 工程師", "custName": "A",
         "link": {"job": "https://www.104.com.tw/job/abc"},
         "descSnippet": "[[[Python]]]", "salaryLow": 0, "salaryHigh": 0},
    ]})


def _detail_resp():
    return httpx.Response(200, json={"data": {
        "jobDetail": {"jobDescription": "JD", "salary": "月薪50,000元", "addressRegion": "台北"},
        "condition": {"workExp": "3年", "edu": "大學", "major": [], "specialty": []},
    }})


async def test_crawl_candidates_stores_candidates():
    db = AsyncMongoMockClient()["test"]
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _search_resp()))
    out = await analyze_svc.crawl_candidates(
        "s1", "u1", "python", None, 1, JobRepository(db), MatchRepository(db),
        http_client=client)
    await client.aclose()
    assert [m.job.job_id for m in out] == ["1"]
    stored = await MatchRepository(db).get_match("s1", "1")
    assert stored.status == "candidate" and stored.relevant is True


async def test_analyze_one_done_and_quota(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    mr, jr, qr = MatchRepository(db), JobRepository(db), QuotaRepository(db)
    job = Job(job_id="1", code="abc", title="t", company="co", url="https://x/abc")
    await mr.add_candidate("s1", "u1", job, relevant=True)

    async def fake_match(target, job, detail, client=None):
        return JobMatch(job=job, score=77, reasons=["r"], gaps=["g"])
    monkeypatch.setattr(analyze_svc.job_matching, "analyze", fake_match)

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _detail_resp()))
    await analyze_svc.analyze_one("s1", "u1", "1", _target(), jr, mr, qr,
                                  http_client=client)
    await client.aclose()
    done = await mr.get_match("s1", "1")
    assert done.status == "done" and done.score == 77
    assert await qr.used_today("u1") == 1


async def test_analyze_one_failure_marks_failed():
    db = AsyncMongoMockClient()["test"]
    mr, jr, qr = MatchRepository(db), JobRepository(db), QuotaRepository(db)
    job = Job(job_id="1", code="abc", title="t", company="co", url="https://x/abc")
    await mr.add_candidate("s1", "u1", job, relevant=True)

    def boom(r): raise httpx.ConnectError("fail")
    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    await analyze_svc.analyze_one("s1", "u1", "1", _target(), jr, mr, qr,
                                  http_client=client)
    await client.aclose()
    assert (await mr.get_match("s1", "1")).status == "failed"
    assert await qr.used_today("u1") == 0  # 失敗不計額度
