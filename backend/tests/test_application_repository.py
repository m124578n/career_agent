# backend/tests/test_application_repository.py
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import ApplicationRepository
from job_tracker.schemas import Application, ApplicationStatus, Job


@pytest.fixture
def repo():
    return ApplicationRepository(AsyncMongoMockClient()["test"])


def _app(user="u1", job_id="1", cover=None) -> Application:
    job = Job(job_id=job_id, code=f"c{job_id}", title="工程師", company="某公司",
              url=f"https://www.104.com.tw/job/c{job_id}")
    return Application(user=user, job_id=job_id, job=job,
                       source_search_id="s1", cover_letter=cover)


async def test_add_and_list(repo: ApplicationRepository):
    await repo.add(_app(cover="信"))
    apps = await repo.list("u1")
    assert len(apps) == 1
    assert apps[0].job_id == "1"
    assert apps[0].status == ApplicationStatus.TO_APPLY
    assert apps[0].cover_letter == "信"


async def test_add_is_deduped(repo: ApplicationRepository):
    await repo.add(_app(cover="原信"))
    await repo.add(_app(cover="新信"))  # 同 user|job_id → 不重複、不覆蓋
    apps = await repo.list("u1")
    assert len(apps) == 1
    assert apps[0].cover_letter == "原信"


async def test_list_isolated_by_user(repo: ApplicationRepository):
    await repo.add(_app(user="u1", job_id="1"))
    await repo.add(_app(user="u2", job_id="2"))
    assert [a.job_id for a in await repo.list("u1")] == ["1"]


async def test_set_status_appends_event(repo: ApplicationRepository):
    await repo.add(_app())
    updated = await repo.set_status("u1", "1", ApplicationStatus.APPLIED)
    assert updated.status == ApplicationStatus.APPLIED
    assert len(updated.events) == 1
    assert updated.events[0].type == "status"
    assert "applied" in updated.events[0].note


async def test_set_status_missing_returns_none(repo: ApplicationRepository):
    assert await repo.set_status("u1", "nope", ApplicationStatus.APPLIED) is None


async def test_remove(repo: ApplicationRepository):
    await repo.add(_app())
    await repo.remove("u1", "1")
    assert await repo.list("u1") == []


async def test_add_note_appends_note_event(repo: ApplicationRepository):
    await repo.add(_app())
    updated = await repo.add_note("u1", "1", "一面聊得不錯")
    assert len(updated.events) == 1
    assert updated.events[0].type == "note"
    assert updated.events[0].note == "一面聊得不錯"


async def test_add_note_missing_returns_none(repo: ApplicationRepository):
    assert await repo.add_note("u1", "nope", "x") is None


async def test_set_offer_persists(repo: ApplicationRepository):
    from job_tracker.schemas import OfferInfo
    await repo.add(_app())
    updated = await repo.set_offer("u1", "1", OfferInfo(salary="月 60k", level="P5"))
    assert updated.offer.salary == "月 60k"
    assert updated.offer.level == "P5"


async def test_set_offer_missing_returns_none(repo: ApplicationRepository):
    from job_tracker.schemas import OfferInfo
    assert await repo.set_offer("u1", "nope", OfferInfo()) is None


async def test_set_result_writes_benefits():
    from job_tracker.db.repositories import MatchRepository
    from job_tracker.schemas import Job, JobMatch
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["test"]
    mr = MatchRepository(db)
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://www.104.com.tw/job/c1")
    await mr.set_match("s1", "u1", JobMatch(job=job, status="pending"))
    analysis = JobMatch(job=job, score=80, reasons=["r"], gaps=["g"],
                        benefits=["遠端一週三天"])
    await mr.set_result("s1", "1", analysis)
    got = await mr.get_match("s1", "1")
    assert got.benefits == ["遠端一週三天"]
    assert got.status == "done"


async def test_set_result_stamps_analyzed_at():
    from job_tracker.db.repositories import MatchRepository
    from job_tracker.schemas import Job, JobMatch
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["test"]
    mr = MatchRepository(db)
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://www.104.com.tw/job/c1")
    await mr.set_match("s1", "u1", JobMatch(job=job, status="pending"))
    pending = await mr.get_match("s1", "1")
    assert pending.analyzed_at is None  # 尚未分析

    analysis = JobMatch(job=job, score=80, reasons=["r"], gaps=["g"])
    await mr.set_result("s1", "1", analysis)
    done = await mr.get_match("s1", "1")
    assert done.status == "done"
    assert done.analyzed_at is not None  # done 後蓋上時間戳
