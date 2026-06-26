"""本機爬蟲 agent：輪詢雲端任務 → 用住宅 IP 抓 104 → 回填原始 JSON。

不依賴 job_tracker 套件。抓 104 用 curl_cffi 模擬 Chrome 的 TLS 指紋
（104 的 WAF 會用 TLS 指紋擋掉 Linux/容器預設的 ClientHello）；
對雲端的 claim/complete 用一般 httpx 即可。解析/LLM 全在雲端。
"""

import asyncio
import logging
import os
import random

import httpx
from curl_cffi.requests import AsyncSession
from dotenv import load_dotenv

log = logging.getLogger("agent")

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{code}"
WARMUP_URL = "https://www.104.com.tw/jobs/search/"

# 模擬的瀏覽器（curl_cffi 會連 TLS/JA3 + 預設 header 一起裝成這個版本）
_IMPERSONATE = "chrome"


def build_104_request(task: dict) -> tuple[str, dict | None, dict]:
    """依任務型別組 104 請求，回傳 (url, params, extra_headers)。純函式，好測試。

    UA / Accept / Accept-Language / sec-ch-ua 等交給 curl_cffi 的 impersonate 處理，
    這裡只補 104 特有的 Referer / X-Requested-With。
    """
    if task["type"] == "search":
        p = task["payload"]
        params = {"ro": 0, "keyword": p["keyword"], "order": 15, "asc": 0,
                  "page": p["page"], "mode": "s", "jobsource": "index_s"}
        if p.get("area"):
            params["area"] = p["area"]
        headers = {"Referer": WARMUP_URL, "X-Requested-With": "XMLHttpRequest"}
        return SEARCH_URL, params, headers
    code = task["payload"]["code"]
    headers = {"Referer": f"https://www.104.com.tw/job/{code}"}
    return DETAIL_URL.format(code=code), None, headers


async def fetch_104(task: dict) -> dict:
    """用 curl_cffi（Chrome TLS 指紋）抓 104，回原始 JSON。每次用獨立 session。"""
    url, params, headers = build_104_request(task)
    async with AsyncSession(impersonate=_IMPERSONATE, timeout=30) as s:
        # 暖身取 WAF/session cookie（同 session）
        try:
            await s.get(WARMUP_URL)
        except Exception as exc:  # noqa: BLE001
            log.warning("暖身失敗（略過）：%s", exc)
        resp = await s.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _task_summary(task: dict) -> str:
    p = task.get("payload", {})
    if task.get("type") == "search":
        return f"keyword={p.get('keyword')!r} page={p.get('page')} area={p.get('area')}"
    return f"code={p.get('code')}"


async def run_once(client: httpx.AsyncClient, cloud_base: str, secret: str,
                   *, fetch=fetch_104) -> str:
    """claim 一次：有任務則抓+complete，回 'done'/'failed'/'idle'。

    `client` 用於對雲端的 claim/complete；`fetch` 負責抓 104（可注入測試）。
    """
    auth = {"Authorization": f"Bearer {secret}"}
    claimed = await client.post(f"{cloud_base}/api/agent/claim", headers=auth)
    claimed.raise_for_status()
    task = claimed.json().get("task")
    if not task:
        return "idle"

    tid = task.get("task_id")
    log.info("認領任務 %s [%s] %s", tid, task.get("type"), _task_summary(task))
    try:
        raw = await fetch(task)
        n = len(raw.get("data", [])) if isinstance(raw.get("data"), list) else "?"
        log.info("抓取 104 成功 task=%s（data 筆數=%s）", tid, n)
    except Exception as exc:  # noqa: BLE001
        log.warning("抓取 104 失敗 task=%s：%s", tid, exc)
        try:
            await client.post(f"{cloud_base}/api/agent/complete", headers=auth,
                              json={"task_id": tid, "error": str(exc)[:500]})
        except Exception as exc2:  # noqa: BLE001
            log.error("回報失敗結果也失敗 task=%s：%s", tid, exc2)
        return "failed"

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
    log.info("agent 啟動，雲端=%s，輪詢每 %ss（104 走 curl_cffi/%s TLS）",
             cloud_base, poll, _IMPERSONATE)

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
                if idle_streak % max(1, int(120 / poll)) == 0:
                    log.info("閒置中…（已處理 %d 筆，持續輪詢）", done_count)
            else:
                idle_streak = 0
                if result == "done":
                    done_count += 1

            if result == "done":
                await asyncio.sleep(random.uniform(min_d, max_d))
            else:
                await asyncio.sleep(poll)


if __name__ == "__main__":
    asyncio.run(main())
