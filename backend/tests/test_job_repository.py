import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import Job, JobDetail


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
