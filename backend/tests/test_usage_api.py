import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.db.repositories import TokenUsageRepository
from job_tracker.main import app


def test_usage_endpoint_returns_summary():
    repo = TokenUsageRepository(AsyncMongoMockClient()["test"])
    asyncio.run(
        repo.record(
            {
                "provider": "foundry",
                "model": "claude-sonnet-4-6",
                "kind": "parse",
                "input_tokens": 100,
                "output_tokens": 40,
                "total_tokens": 140,
            }
        )
    )

    app.dependency_overrides[deps.get_usage_repo] = lambda: repo
    try:
        resp = TestClient(app).get("/api/usage")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_tokens"] == 140
    assert body["calls"] == 1
    assert body["by_model"]["claude-sonnet-4-6"] == 140
