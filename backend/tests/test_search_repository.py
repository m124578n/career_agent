# backend/tests/test_search_repository.py
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import SearchRepository
from job_tracker.schemas import ResumeTarget


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test"]


def _target() -> ResumeTarget:
    return ResumeTarget(target_title="後端工程師", resume_text="Python")


async def test_create_and_get(db):
    repo = SearchRepository(db)
    run = await repo.create("u1", "python", _target())
    assert run.search_id
    got = await repo.get(run.search_id)
    assert got is not None
    assert got.keyword == "python"
    assert got.user == "u1"


async def test_list_sorted_desc(db):
    repo = SearchRepository(db)
    a = await repo.create("u1", "first", _target())
    b = await repo.create("u1", "second", _target())
    await repo.create("u2", "other", _target())
    runs = await repo.list("u1")
    assert [r.search_id for r in runs] == [b.search_id, a.search_id]  # 新到舊


async def test_advance_updates_offset_and_count(db):
    repo = SearchRepository(db)
    run = await repo.create("u1", "python", _target())
    await repo.advance(run.search_id, next_offset=5, count_delta=3)
    await repo.advance(run.search_id, next_offset=10, count_delta=2)
    got = await repo.get(run.search_id)
    assert got.next_offset == 10
    assert got.count == 5


async def test_delete_cascades_matches(db):
    from job_tracker.db.repositories import MatchRepository
    from job_tracker.schemas import Job, JobMatch
    search_repo = SearchRepository(db)
    match_repo = MatchRepository(db)
    run = await search_repo.create("u1", "python", _target())
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://x/1")
    await match_repo.set_match(run.search_id, "u1",
                               JobMatch(job=job, score=80, reasons=["r"], gaps=["g"]))
    await search_repo.delete(run.search_id)
    assert await search_repo.get(run.search_id) is None
    assert await match_repo.list_by_search(run.search_id) == []
