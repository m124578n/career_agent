from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import usage as usage_router
from job_tracker.main import app


def test_admin_stats_ok_for_admin_in_dev():
    db = AsyncMongoMockClient()["test"]
    app.dependency_overrides[deps.get_database] = lambda: db
    try:
        # dev 模式 → dev@local 視為 admin
        resp = TestClient(app).get("/api/usage/admin-stats")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    body = resp.json()
    assert {"total_users", "active_7d", "daily_active", "tokens"} <= set(body)
    assert len(body["daily_active"]) == 30


def test_admin_stats_forbidden_for_non_admin(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    monkeypatch.setattr(usage_router, "is_admin", lambda user: False)
    app.dependency_overrides[deps.get_database] = lambda: db
    try:
        resp = TestClient(app).get("/api/usage/admin-stats")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403
