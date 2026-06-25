"""本機爬蟲 agent：輪詢雲端任務 → 用住宅 IP 抓 104 → 回填原始 JSON。

不依賴 job_tracker 套件；只用 httpx。解析/LLM 全在雲端。
"""

import asyncio
import os
import random

import httpx
from dotenv import load_dotenv

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{code}"
WARMUP_URL = "https://www.104.com.tw/jobs/search/"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
_SEARCH_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://www.104.com.tw/jobs/search/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
}


async def _warmup(client: httpx.AsyncClient) -> None:
    try:
        await client.get(WARMUP_URL, headers={"User-Agent": _UA})
    except httpx.HTTPError:
        pass


async def fetch_104(task: dict, client: httpx.AsyncClient) -> dict:
    """依任務型別抓 104，回原始 JSON。"""
    await _warmup(client)
    if task["type"] == "search":
        p = task["payload"]
        params = {"ro": 0, "keyword": p["keyword"], "order": 15, "asc": 0,
                  "page": p["page"], "mode": "s", "jobsource": "index_s"}
        if p.get("area"):
            params["area"] = p["area"]
        resp = await client.get(SEARCH_URL, params=params, headers=_SEARCH_HEADERS)
    else:  # detail
        code = task["payload"]["code"]
        headers = {"User-Agent": _UA, "Referer": f"https://www.104.com.tw/job/{code}",
                   "Accept": "application/json, text/plain, */*"}
        resp = await client.get(DETAIL_URL.format(code=code), headers=headers)
    resp.raise_for_status()
    return resp.json()


async def run_once(client: httpx.AsyncClient, cloud_base: str, secret: str) -> str:
    """claim 一次：有任務則抓+complete，回 'done'/'failed'/'idle'。"""
    auth = {"Authorization": f"Bearer {secret}"}
    claimed = await client.post(f"{cloud_base}/api/agent/claim", headers=auth)
    claimed.raise_for_status()
    task = claimed.json().get("task")
    if not task:
        return "idle"
    try:
        raw = await fetch_104(task, client)
        await client.post(f"{cloud_base}/api/agent/complete", headers=auth,
                          json={"task_id": task["task_id"], "raw_json": raw})
        return "done"
    except Exception as exc:  # noqa: BLE001
        await client.post(f"{cloud_base}/api/agent/complete", headers=auth,
                          json={"task_id": task["task_id"], "error": str(exc)})
        return "failed"


async def main() -> None:
    load_dotenv()
    cloud_base = os.environ["CLOUD_BASE_URL"].rstrip("/")
    secret = os.environ["AGENT_SECRET"]
    poll = float(os.environ.get("POLL_INTERVAL", "3"))
    min_d = float(os.environ.get("MIN_DELAY", "2"))
    max_d = float(os.environ.get("MAX_DELAY", "5"))
    print(f"agent 啟動，雲端={cloud_base}，輪詢每 {poll}s")
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        while True:
            try:
                result = await run_once(client, cloud_base, secret)
            except Exception as exc:  # noqa: BLE001
                print("輪詢錯誤：", exc)
                result = "error"
            if result == "done":
                # 抓完一筆後節流，避免連續打 104
                await asyncio.sleep(random.uniform(min_d, max_d))
            else:
                await asyncio.sleep(poll)


if __name__ == "__main__":
    asyncio.run(main())
