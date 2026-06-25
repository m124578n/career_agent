"""本機爬蟲 agent：輪詢雲端任務 → 用住宅 IP 抓 104 → 回填原始 JSON。

不依賴 job_tracker 套件；只用 httpx。解析/LLM 全在雲端。
"""

import asyncio
import logging
import os
import random

import httpx
from dotenv import load_dotenv

log = logging.getLogger("agent")

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
    """每次抓取前先 GET 搜尋頁取得新鮮的 WAF/session cookie。

    註：曾為了少打 104 改成「整個 process 只暖一次」，但長時間跑著 cookie 會過期，
    導致後續 detail 抓取被 104 回 403。改回每次抓取前都暖身（多一個 GET 但確保有效）。
    """
    try:
        await client.get(WARMUP_URL, headers={"User-Agent": _UA})
    except httpx.HTTPError as exc:
        log.warning("暖身失敗（略過）：%s", exc)


def _task_summary(task: dict) -> str:
    """任務的簡短描述，供 log 用。"""
    p = task.get("payload", {})
    if task.get("type") == "search":
        return f"keyword={p.get('keyword')!r} page={p.get('page')} area={p.get('area')}"
    return f"code={p.get('code')}"


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

    tid = task.get("task_id")
    log.info("認領任務 %s [%s] %s", tid, task.get("type"), _task_summary(task))
    try:
        raw = await fetch_104(task, client)
        n = len(raw.get("data", [])) if isinstance(raw.get("data"), list) else "?"
        log.info("抓取 104 成功 task=%s（data 筆數=%s）", tid, n)
    except Exception as exc:  # noqa: BLE001
        # 抓 104 失敗：回報 error 給雲端（這段以前是靜默的，現在記下原因）
        log.warning("抓取 104 失敗 task=%s：%s", tid, exc)
        try:
            await client.post(f"{cloud_base}/api/agent/complete", headers=auth,
                              json={"task_id": tid, "error": str(exc)[:500]})
        except Exception as exc2:  # noqa: BLE001
            log.error("回報失敗結果也失敗 task=%s：%s", tid, exc2)
        return "failed"

    # 抓取成功 → 回填原始 JSON
    try:
        resp = await client.post(f"{cloud_base}/api/agent/complete", headers=auth,
                                 json={"task_id": tid, "raw_json": raw})
        resp.raise_for_status()
        log.info("回填完成 task=%s → 雲端 %s", tid, resp.json().get("status", "?"))
    except Exception as exc:  # noqa: BLE001
        log.warning("回填雲端失敗 task=%s：%s", tid, exc)
        return "failed"
    return "done"


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    load_dotenv()
    cloud_base = os.environ["CLOUD_BASE_URL"].rstrip("/")
    secret = os.environ["AGENT_SECRET"]
    poll = float(os.environ.get("POLL_INTERVAL", "3"))
    min_d = float(os.environ.get("MIN_DELAY", "2"))
    max_d = float(os.environ.get("MAX_DELAY", "5"))
    log.info("agent 啟動，雲端=%s，輪詢每 %ss", cloud_base, poll)

    idle_streak = 0
    done_count = 0
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        while True:
            try:
                result = await run_once(client, cloud_base, secret)
            except Exception as exc:  # noqa: BLE001
                log.error("輪詢錯誤（claim 失敗？認證？網路？）：%s", exc)
                result = "error"

            if result == "idle":
                idle_streak += 1
                # 閒置不洗版，但每 ~2 分鐘報一次活著
                if idle_streak % max(1, int(120 / poll)) == 0:
                    log.info("閒置中…（已處理 %d 筆，持續輪詢）", done_count)
            else:
                idle_streak = 0
                if result == "done":
                    done_count += 1

            if result == "done":
                await asyncio.sleep(random.uniform(min_d, max_d))  # 抓完節流
            else:
                await asyncio.sleep(poll)


if __name__ == "__main__":
    asyncio.run(main())
