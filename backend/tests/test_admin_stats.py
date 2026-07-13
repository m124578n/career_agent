import asyncio
from datetime import UTC, datetime, timedelta

from mongomock_motor import AsyncMongoMockClient

from job_tracker.services.admin_stats import compute_admin_stats


def _day(offset: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=offset)).isoformat()


def _seed(db):
    du = db["daily_usage"]
    # 三個使用者：a 今天、b 5 天前、c 20 天前
    asyncio.run(du.insert_many([
        {"_id": f"a|{_day(0)}", "user": "a", "day": _day(0), "count": 3},
        {"_id": f"b|{_day(5)}", "user": "b", "day": _day(5), "count": 1},
        {"_id": f"c|{_day(20)}", "user": "c", "day": _day(20), "count": 2},
    ]))
    asyncio.run(db["searches"].insert_many([{"_id": "s1"}, {"_id": "s2"}]))
    asyncio.run(db["matches"].insert_many([
        {"_id": "m1", "status": "done"}, {"_id": "m2", "status": "done"},
        {"_id": "m3", "status": "candidate"},
    ]))
    asyncio.run(db["applications"].insert_one({"_id": "app1", "user": "a"}))
    asyncio.run(db["token_usage"].insert_many([
        {"user": "a", "total_tokens": 100}, {"user": "b", "total_tokens": 50},
    ]))


def test_compute_admin_stats_aggregates():
    db = AsyncMongoMockClient()["test"]
    _seed(db)
    s = asyncio.run(compute_admin_stats(db))
    assert s.total_users == 3           # a, b, c
    assert s.active_7d == 2             # a(0), b(5)
    assert s.active_30d == 3            # a, b, c
    assert s.total_searches == 2
    assert s.total_analyzed == 2        # 只算 done
    assert s.total_applications == 1
    assert s.tokens == 150 and s.llm_calls == 2
    assert len(s.daily_active) == 30    # 連續 30 天
    assert s.daily_active[-1].day == _day(0) and s.daily_active[-1].users == 1
    assert s.daily_active[0].day == _day(29)


def test_compute_admin_stats_empty():
    db = AsyncMongoMockClient()["test"]
    s = asyncio.run(compute_admin_stats(db))
    assert s.total_users == 0 and s.active_7d == 0 and s.tokens == 0
    assert len(s.daily_active) == 30 and all(d.users == 0 for d in s.daily_active)
