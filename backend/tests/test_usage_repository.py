import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import TokenUsageRepository


@pytest.fixture
def repo() -> TokenUsageRepository:
    return TokenUsageRepository(AsyncMongoMockClient()["test"])


def rec(model: str, inp: int, out: int) -> dict:
    return {
        "provider": "foundry",
        "model": model,
        "kind": "parse",
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
    }


async def test_record_and_summary(repo: TokenUsageRepository):
    await repo.record(rec("claude-sonnet-4-6", 100, 40))
    await repo.record(rec("claude-sonnet-4-6", 200, 60))

    s = await repo.summary()
    assert s["calls"] == 2
    assert s["input_tokens"] == 300
    assert s["output_tokens"] == 100
    assert s["total_tokens"] == 400


async def test_summary_breaks_down_by_model(repo: TokenUsageRepository):
    await repo.record(rec("claude-sonnet-4-6", 100, 40))
    await repo.record(rec("gpt-4o-mini", 50, 10))

    s = await repo.summary()
    assert s["by_model"]["claude-sonnet-4-6"] == 140
    assert s["by_model"]["gpt-4o-mini"] == 60


async def test_empty_summary(repo: TokenUsageRepository):
    s = await repo.summary()
    assert s["calls"] == 0
    assert s["total_tokens"] == 0


async def test_summary_scoped_by_user(repo: TokenUsageRepository):
    await repo.record({**rec("m", 10, 5), "user": "a"})
    await repo.record({**rec("m", 20, 10), "user": "b"})

    assert (await repo.summary("a"))["total_tokens"] == 15
    assert (await repo.summary("b"))["total_tokens"] == 30
    assert (await repo.summary())["total_tokens"] == 45  # 全站
