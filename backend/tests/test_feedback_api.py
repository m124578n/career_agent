import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import feedback as feedback_router
from job_tracker.db.repositories import FeedbackRepository
from job_tracker.main import app


def _client_with(repo):
    app.dependency_overrides[deps.get_feedback_repo] = lambda: repo
    return TestClient(app)


def test_submit_ok_for_any_user():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    try:
        r = _client_with(repo).post("/api/feedback", json={"message": "很好用", "category": "建議"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200 and r.json()["ok"] is True
    assert asyncio.run(repo.list())[0].message == "很好用"


def test_submit_empty_400():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    try:
        r = _client_with(repo).post("/api/feedback", json={"message": "   "})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400


def test_submit_too_long_400():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    try:
        r = _client_with(repo).post("/api/feedback", json={"message": "x" * 2001})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 400


def test_list_admin_ok_nonadmin_403():
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    asyncio.run(repo.create("u@x.com", "hi", "其他"))
    # admin（dev 模式）
    try:
        r = _client_with(repo).get("/api/feedback")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200 and len(r.json()) == 1


def test_list_forbidden_for_nonadmin(monkeypatch):
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    monkeypatch.setattr(feedback_router, "is_admin", lambda user: False)
    try:
        r = _client_with(repo).get("/api/feedback")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 403


def test_read_and_delete_admin(monkeypatch):
    repo = FeedbackRepository(AsyncMongoMockClient()["test"])
    fb = asyncio.run(repo.create("u@x.com", "hi", "其他"))
    c = _client_with(repo)
    try:
        assert c.post(f"/api/feedback/{fb.id}/read", json={"read": True}).status_code == 200
        assert asyncio.run(repo.list())[0].read is True
        assert c.delete(f"/api/feedback/{fb.id}").status_code == 200
        assert asyncio.run(repo.list()) == []
        # 非 admin 被擋
        monkeypatch.setattr(feedback_router, "is_admin", lambda user: False)
        assert c.delete("/api/feedback/whatever").status_code == 403
    finally:
        app.dependency_overrides.clear()
