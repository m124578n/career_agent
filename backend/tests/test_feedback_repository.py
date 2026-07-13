import asyncio

from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import FeedbackRepository


def _repo():
    return FeedbackRepository(AsyncMongoMockClient()["test"])


def test_create_sets_fields():
    repo = _repo()
    fb = asyncio.run(repo.create("a@x.com", " 很好用 ", "建議"))
    assert fb.user == "a@x.com" and fb.message == " 很好用 " and fb.category == "建議"
    assert fb.read is False and fb.id and fb.created_at


def test_list_newest_first():
    repo = _repo()
    a = asyncio.run(repo.create("a@x.com", "first", "其他"))
    b = asyncio.run(repo.create("b@x.com", "second", "其他"))
    items = asyncio.run(repo.list())
    assert [i.id for i in items] == [b.id, a.id]  # 新→舊
    assert all(i.id for i in items)  # id 有從 _id 帶回


def test_mark_read_and_delete():
    repo = _repo()
    fb = asyncio.run(repo.create("a@x.com", "x", "其他"))
    asyncio.run(repo.mark_read(fb.id, True))
    assert asyncio.run(repo.list())[0].read is True
    asyncio.run(repo.delete(fb.id))
    assert asyncio.run(repo.list()) == []
