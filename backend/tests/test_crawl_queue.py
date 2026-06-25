import pytest
from datetime import UTC, datetime, timedelta
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


@pytest.mark.asyncio
async def test_complete_stores_raw_and_marks_done():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    await repo.claim()
    done = await repo.complete("t1", {"data": [{"jobNo": "1"}]})
    assert done.status == "done"
    assert done.raw_json == {"data": [{"jobNo": "1"}]}
    assert done.completed_at is not None


@pytest.mark.asyncio
async def test_fail_marks_failed_with_error():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    await repo.claim()
    failed = await repo.fail("t1", "403 Forbidden")
    assert failed.status == "failed"
    assert failed.error == "403 Forbidden"


@pytest.mark.asyncio
async def test_reap_expires_old_pending():
    db = AsyncMongoMockClient()["test"]
    repo = CrawlTaskRepository(db)
    await repo.enqueue(_task("old"))
    # 手動把 created_at 改成 25 小時前
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    await db["crawl_tasks"].update_one({"_id": "old"}, {"$set": {"created_at": old}})
    await repo.reap(pending_ttl_sec=24 * 3600, claimed_ttl_sec=300)
    assert (await repo.get("old")).status == "expired"


@pytest.mark.asyncio
async def test_reap_requeues_stale_claimed():
    db = AsyncMongoMockClient()["test"]
    repo = CrawlTaskRepository(db)
    await repo.enqueue(_task("stuck"))
    await repo.claim()
    stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    await db["crawl_tasks"].update_one({"_id": "stuck"}, {"$set": {"claimed_at": stale}})
    await repo.reap(pending_ttl_sec=24 * 3600, claimed_ttl_sec=300)
    t = await repo.get("stuck")
    assert t.status == "pending"
    assert t.claimed_at is None
