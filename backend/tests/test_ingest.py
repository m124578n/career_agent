import json
from pathlib import Path

from mongomock_motor import AsyncMongoMockClient

from job_tracker.crawler import parse_job_detail, parse_jobs
from job_tracker.db.repositories import JobRepository
from job_tracker.services import ingest as ingest_svc

FIXTURES = Path(__file__).parent / "fixtures"
SEARCH = json.loads((FIXTURES / "104_search.json").read_text(encoding="utf-8"))
DETAIL = json.loads((FIXTURES / "104_detail.json").read_text(encoding="utf-8"))


async def test_ingest_stores_jobs_and_details(monkeypatch):
    repo = JobRepository(AsyncMongoMockClient()["test"])
    jobs = parse_jobs(SEARCH)
    detail = parse_job_detail(DETAIL)

    async def fake_crawl(keyword, *, page=1, area=None, session=None):
        return [(j, True) for j in jobs]

    async def fake_details(codes, *, session=None, min_delay=2.0, max_delay=5.0):
        return [detail for _ in codes]

    monkeypatch.setattr(ingest_svc, "crawl_jobs", fake_crawl)
    monkeypatch.setattr(ingest_svc, "crawl_job_details", fake_details)

    out = await ingest_svc.ingest_jobs("python", repo)

    assert len(out) == 2
    stored = await repo.list_jobs()
    assert len(stored) == 2
    # 詳情有被抓並存入
    d = await repo.get_detail(out[0].job_id)
    assert d is not None
    assert d.salary == "待遇面議"
