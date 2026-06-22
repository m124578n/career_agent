import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import JobRepository, MatchRepository
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


@pytest.fixture
def match_repo() -> MatchRepository:
    return MatchRepository(AsyncMongoMockClient()["test"])


async def test_set_and_list_by_search_sorted(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 60))
    await match_repo.set_match("s1", "u1", make_match("2", 90))
    matches = await match_repo.list_by_search("s1")
    assert [m.score for m in matches] == [90, 60]
    assert matches[0].job.job_id == "2"


async def test_matches_isolated_by_search(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 50))
    await match_repo.set_match("s2", "u1", make_match("2", 80))
    assert [m.job.job_id for m in await match_repo.list_by_search("s1")] == ["1"]
    assert [m.job.job_id for m in await match_repo.list_by_search("s2")] == ["2"]


async def test_get_match(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 70))
    m = await match_repo.get_match("s1", "1")
    assert m is not None and m.score == 70
    assert await match_repo.get_match("s1", "nope") is None


async def test_set_cover_letter_persists(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 70))
    await match_repo.set_cover_letter("s1", "1", "敬啟者，求職信內容。")
    m = await match_repo.get_match("s1", "1")
    assert m.cover_letter == "敬啟者，求職信內容。"
