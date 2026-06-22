import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.db.repositories import QuotaRepository, TokenUsageRepository
from job_tracker.main import app


def _rec(user: str, total: int) -> dict:
    return {
        "user": user,
        "provider": "foundry",
        "model": "claude-sonnet-4-6",
        "kind": "parse",
        "input_tokens": total,
        "output_tokens": 0,
        "total_tokens": total,
    }


def test_my_usage_scoped_to_user():
    repo = TokenUsageRepository(AsyncMongoMockClient()["test"])
    asyncio.run(repo.record(_rec("dev@local", 140)))
    asyncio.run(repo.record(_rec("someone@else", 999)))

    app.dependency_overrides[deps.get_usage_repo] = lambda: repo
    try:
        resp = TestClient(app).get("/api/usage")  # 未設 google → user=dev@local
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["total_tokens"] == 140  # 只算自己


def test_global_usage_allowed_for_admin_in_dev():
    repo = TokenUsageRepository(AsyncMongoMockClient()["test"])
    asyncio.run(repo.record(_rec("dev@local", 140)))
    asyncio.run(repo.record(_rec("someone@else", 60)))

    app.dependency_overrides[deps.get_usage_repo] = lambda: repo
    try:
        # 本機停用驗證 → dev@local 視為 admin
        resp = TestClient(app).get("/api/usage/global")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["total_tokens"] == 200  # 全站加總


def test_quota_reports_is_admin():
    # 用 mongomock 取代真 db，避免測試依賴外部 Atlas
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(
        AsyncMongoMockClient()["test"]
    )
    try:
        resp = TestClient(app).get("/api/usage/quota")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_admin"] is True  # dev 模式
    assert body["limit"] == 50
