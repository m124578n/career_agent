import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import Job, JobDetail, JobMatch


@pytest.fixture
def repo() -> JobRepository:
    db = AsyncMongoMockClient()["test"]
    return JobRepository(db)


def make_job(job_id: str = "1", code: str = "abc") -> Job:
    return Job(
        job_id=job_id,
        code=code,
        title="工程師",
        company="某公司",
        url=f"https://www.104.com.tw/job/{code}",
        salary="面議",
    )


async def test_upsert_and_get_job(repo: JobRepository):
    await repo.upsert_job(make_job())
    got = await repo.get_job("1")
    assert got is not None
    assert got.job_id == "1"
    assert got.code == "abc"
    assert got.company == "某公司"


async def test_get_missing_job_returns_none(repo: JobRepository):
    assert await repo.get_job("nope") is None


async def test_upsert_is_idempotent(repo: JobRepository):
    await repo.upsert_job(make_job())
    await repo.upsert_job(make_job())  # 同 job_id 重複，不應產生兩筆
    jobs = await repo.list_jobs()
    assert len(jobs) == 1


async def test_set_and_get_detail(repo: JobRepository):
    await repo.upsert_job(make_job())
    detail = JobDetail(description="完整 JD", salary="月薪50,000元", specialties=["Python"])
    await repo.set_detail("1", detail)

    got = await repo.get_detail("1")
    assert got is not None
    assert got.description == "完整 JD"
    assert got.specialties == ["Python"]


def make_match(job_id: str, score: int) -> JobMatch:
    return JobMatch(
        job=make_job(job_id, code=f"c{job_id}"),
        score=score,
        reasons=["理由"],
        gaps=["缺口"],
    )


async def test_set_and_list_matches_sorted(repo: JobRepository):
    await repo.upsert_job(make_job("1", "c1"))
    await repo.upsert_job(make_job("2", "c2"))
    await repo.set_match("1", make_match("1", 60))
    await repo.set_match("2", make_match("2", 90))

    matches = await repo.list_matches()
    assert [m.score for m in matches] == [90, 60]  # 由高到低
    assert matches[0].job.job_id == "2"
    assert matches[0].reasons == ["理由"]


async def test_list_matches_skips_unanalyzed(repo: JobRepository):
    await repo.upsert_job(make_job("1", "c1"))  # 沒分析
    await repo.upsert_job(make_job("2", "c2"))
    await repo.set_match("2", make_match("2", 75))

    matches = await repo.list_matches()
    assert [m.job.job_id for m in matches] == ["2"]
