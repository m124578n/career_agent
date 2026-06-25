import httpx
import pytest

from agent import fetch_104, run_once

SEARCH_TASK = {"task_id": "t1", "type": "search",
               "payload": {"keyword": "ai", "page": 1, "area": "6001001000"}}
DETAIL_TASK = {"task_id": "t2", "type": "detail", "payload": {"code": "8rl43"}}


@pytest.mark.asyncio
async def test_fetch_104_search_hits_search_api():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"data": [{"jobNo": "1"}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await fetch_104(SEARCH_TASK, client)
    await client.aclose()
    assert out == {"data": [{"jobNo": "1"}]}
    assert "search/api/jobs" in seen["url"]
    assert "keyword=ai" in seen["url"]


@pytest.mark.asyncio
async def test_run_once_claims_fetches_completes():
    calls = []

    def handler(req):
        path = req.url.path
        calls.append(path)
        if path.endswith("/api/agent/claim"):
            return httpx.Response(200, json={"task": SEARCH_TASK})
        if "search/api/jobs" in str(req.url):
            return httpx.Response(200, json={"data": []})
        if path.endswith("/api/agent/complete"):
            return httpx.Response(200, json={"ok": True, "status": "done"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await run_once(client, "http://cloud", "sek")
    await client.aclose()
    assert result == "done"
    assert "/api/agent/claim" in calls and "/api/agent/complete" in calls


@pytest.mark.asyncio
async def test_run_once_idle_when_no_task():
    def handler(req):
        return httpx.Response(200, json={"task": None})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await run_once(client, "http://cloud", "sek")
    await client.aclose()
    assert result == "idle"
