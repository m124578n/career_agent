from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository,
)
from job_tracker.schemas import Job, JobDetail, JobMatch, ResumeTarget
from job_tracker.services import analyze as analyze_svc


def _target():
    return ResumeTarget(target_title="後端", resume_text="Python")


def _detail() -> JobDetail:
    return JobDetail(description="JD", salary="月薪50,000元", location="台北",
                     work_exp="3年", education="大學")


async def test_crawl_candidates_stores_candidates(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    job = Job(job_id="1", code="abc", title="Python 工程師", company="A",
              url="https://www.104.com.tw/job/abc")

    async def fake_crawl(keyword, *, page=1, area=None, session=None):
        return [(job, True)]
    monkeypatch.setattr(analyze_svc, "crawl_jobs", fake_crawl)

    out = await analyze_svc.crawl_candidates(
        "s1", "u1", "python", None, 1, JobRepository(db), MatchRepository(db))
    assert [m.job.job_id for m in out] == ["1"]
    stored = await MatchRepository(db).get_match("s1", "1")
    assert stored.status == "candidate" and stored.relevant is True


async def test_analyze_one_done_and_quota(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    mr, jr, qr = MatchRepository(db), JobRepository(db), QuotaRepository(db)
    job = Job(job_id="1", code="abc", title="t", company="co", url="https://x/abc")
    await mr.add_candidate("s1", "u1", job, relevant=True)

    async def fake_detail(code, *, session=None):
        return _detail()
    monkeypatch.setattr(analyze_svc, "fetch_job_detail", fake_detail)

    async def fake_match(target, job, detail, client=None):
        return JobMatch(job=job, score=77, reasons=["r"], gaps=["g"])
    monkeypatch.setattr(analyze_svc.job_matching, "analyze", fake_match)

    await analyze_svc.analyze_one("s1", "u1", "1", _target(), jr, mr, qr)
    done = await mr.get_match("s1", "1")
    assert done.status == "done" and done.score == 77
    assert await qr.used_today("u1") == 1


async def test_analyze_one_failure_marks_failed(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    mr, jr, qr = MatchRepository(db), JobRepository(db), QuotaRepository(db)
    job = Job(job_id="1", code="abc", title="t", company="co", url="https://x/abc")
    await mr.add_candidate("s1", "u1", job, relevant=True)

    async def boom(code, *, session=None):
        raise RuntimeError("fail")
    monkeypatch.setattr(analyze_svc, "fetch_job_detail", boom)

    await analyze_svc.analyze_one("s1", "u1", "1", _target(), jr, mr, qr)
    assert (await mr.get_match("s1", "1")).status == "failed"
    assert await qr.used_today("u1") == 0  # 失敗不計額度
