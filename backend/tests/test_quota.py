import asyncio

import pytest
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.db.repositories import QuotaRepository
from job_tracker.main import app


@pytest.fixture
def quota() -> QuotaRepository:
    return QuotaRepository(AsyncMongoMockClient()["test"])


async def test_used_today_starts_zero(quota: QuotaRepository):
    assert await quota.used_today("u") == 0


async def test_add_accumulates(quota: QuotaRepository):
    await quota.add("u", 3)
    await quota.add("u", 2)
    assert await quota.used_today("u") == 5


async def test_quota_per_user(quota: QuotaRepository):
    await quota.add("a", 1)
    assert await quota.used_today("b") == 0


def test_diagnose_429_when_quota_exhausted():
    db = AsyncMongoMockClient()["test"]
    quota = QuotaRepository(db)
    asyncio.run(quota.add("dev@local", 50))  # 預設上限 50，已用滿

    app.dependency_overrides[deps.get_quota_repo] = lambda: quota
    try:
        resp = TestClient(app).post(
            "/api/resumes/diagnose",
            json={
                "target_title": "後端工程師",
                "expected_salary": 70000,
                "resume_text": "Python",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 429
