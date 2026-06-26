import httpx
import pytest

from agent import build_104_request, run_once

SEARCH_TASK = {"task_id": "t1", "type": "search",
               "payload": {"keyword": "ai", "page": 1, "area": "6001001000"}}
DETAIL_TASK = {"task_id": "t2", "type": "detail", "payload": {"code": "8rl43"}}


def test_build_search_request():
    url, params, headers = build_104_request(SEARCH_TASK)
    assert "search/api/jobs" in url
    assert params["keyword"] == "ai" and params["page"] == 1
    assert params["area"] == "6001001000"
    assert headers["X-Requested-With"] == "XMLHttpRequest"


def test_build_detail_request():
    url, params, headers = build_104_request(DETAIL_TASK)
    assert url.endswith("/job/ajax/content/8rl43")
    assert params is None
    assert headers["Referer"].endswith("/job/8rl43")


@pytest.mark.asyncio
async def test_run_once_claims_fetches_completes():
    calls = []

    def handler(req):
        path = req.url.path
        calls.append(path)
        if path.endswith("/api/agent/claim"):
            return httpx.Response(200, json={"task": SEARCH_TASK})
        if path.endswith("/api/agent/complete"):
            return httpx.Response(200, json={"ok": True, "status": "done"})
        return httpx.Response(404)

    async def fake_fetch(task):
        assert task == SEARCH_TASK
        return {"data": []}

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await run_once(client, "http://cloud", "sek", fetch=fake_fetch)
    await client.aclose()
    assert result == "done"
    assert "/api/agent/claim" in calls and "/api/agent/complete" in calls


@pytest.mark.asyncio
async def test_run_once_reports_failure_on_fetch_error():
    posted = {}

    def handler(req):
        path = req.url.path
        if path.endswith("/api/agent/claim"):
            return httpx.Response(200, json={"task": DETAIL_TASK})
        if path.endswith("/api/agent/complete"):
            import json as _json
            posted.update(_json.loads(req.content))
            return httpx.Response(200, json={"ok": True, "status": "failed"})
        return httpx.Response(404)

    async def boom(task):
        raise RuntimeError("403 Forbidden")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await run_once(client, "http://cloud", "sek", fetch=boom)
    await client.aclose()
    assert result == "failed"
    assert posted["task_id"] == "t2"
    assert "403" in posted["error"]


@pytest.mark.asyncio
async def test_run_once_idle_when_no_task():
    def handler(req):
        return httpx.Response(200, json={"task": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await run_once(client, "http://cloud", "sek")
    await client.aclose()
    assert result == "idle"
