import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import CrawlTaskRepository
from job_tracker.schemas import CrawlTask


def _task(task_id="t1", type="search"):
    return CrawlTask(task_id=task_id, type=type,
                     payload={"keyword": "ai", "page": 1, "area": None},
                     search_id="s1", user="u@x")


@pytest.mark.asyncio
async def test_enqueue_then_claim_returns_pending_task():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    claimed = await repo.claim()
    assert claimed is not None
    assert claimed.task_id == "t1"
    assert claimed.status == "claimed"
    assert claimed.claimed_at is not None


@pytest.mark.asyncio
async def test_claim_is_atomic_no_double_claim():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    first = await repo.claim()
    second = await repo.claim()  # 已無 pending
    assert first is not None and first.task_id == "t1"
    assert second is None


@pytest.mark.asyncio
async def test_claim_returns_none_when_empty():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    assert await repo.claim() is None
