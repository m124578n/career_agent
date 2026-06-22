# 候選勾選 + 非同步逐筆分析 + 選地區 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把職缺分析改成兩階段（爬 104 候選清單 → 使用者勾選 → 只分析選中的），分析改非同步逐筆背景執行＋前端輪詢，並新增縣市地區篩選。

**Architecture:** 爬取階段把候選存成 `matches` 文件的 `candidate` placeholder（含 `relevant` 命中標記）；分析階段標 `pending` 並用可注入的 `AnalysisRunner` 背景逐筆處理（`done`/`failed`），抓 104 詳情經全域 semaphore 節流。前端先呈現可勾選候選清單，送出後輪詢逐筆顯示。

**Tech Stack:** FastAPI + motor（mongomock-motor 測試）、Pydantic v2、Python 3.14/uv、httpx、React + Vite + TS + Mantine + React Query。

## Global Constraints

- TDD 嚴格 Red-Green-Refactor。後端測試 `cd backend && uv run pytest`；前端 `cd frontend && npm run build`。
- 測試環境 `GOOGLE_CLIENT_ID=""`（conftest 已設），user 預設 `dev@local`。
- 額度：analyze 提交時檢查「剩餘 ≥ 選中數」否則 429；每筆 done 才 `quota.add(1)`，failed 不計。
- 反爬：抓 104 詳情經全域 `asyncio.Semaphore`（上限 2）；逐筆間保留 2–5 秒節流。
- **已知限制（須保留在程式碼註解與 PROGRESS）**：(1) 額度寬鬆策略可能短暫超賣；(2) 背景任務不持久化，server 重啟未完成的卡 `pending`，靠前端重試。
- 跨使用者隔離：所有 `{search_id}` 端點過 `_ensure_owned`；analyze 另驗 job_ids 屬該 search。
- 104 area 代碼實測有效：台北市 `6001001000`、新竹市 `6001006000`。
- Commit 訊息結尾：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

- `backend/src/job_tracker/schemas/__init__.py` — `JobMatch` 欄位 optional + `status`/`relevant`；`SearchRun` 加 `area`/`next_page`
- `backend/src/job_tracker/crawler/__init__.py` — `crawl_jobs` 加 `area`、回傳帶 `relevant`
- `backend/src/job_tracker/db/repositories.py` — `MatchRepository` candidate/status 方法；`SearchRepository` area/next_page
- `backend/src/job_tracker/services/analyze.py` — 拆 `crawl_candidates` + `analyze_one` + `AnalysisRunner` + 全域 semaphore
- `backend/src/job_tracker/api/deps.py` — `get_analysis_runner`
- `backend/src/job_tracker/api/routers/jobs.py` — 兩階段端點
- 前端 `types/index.ts`、`api/client.ts`、`constants/regions.ts`（新）、`pages/JobList.tsx`
- 測試：對應各 `backend/tests/test_*.py`

---

## Task 1: Schema 改造

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py`
- Test: `backend/tests/test_schemas.py`

**Interfaces:**
- Produces: `JobMatch(job, score=0.0, reasons=[], gaps=[], requires_external_apply=False, cover_letter=None, status="done", relevant=True)`；`SearchRun(..., area:str|None=None, next_page:int=1, count:int=0)`（移除 `next_offset`）

- [ ] **Step 1: 寫失敗測試**（append 到 `test_schemas.py`）

```python
def test_jobmatch_candidate_defaults():
    from job_tracker.schemas import Job, JobMatch
    job = Job(job_id="1", code="c1", title="t", company="co", url="https://x/1")
    m = JobMatch(job=job)  # candidate 階段：還沒有分數
    assert m.score == 0
    assert m.reasons == [] and m.gaps == []
    assert m.status == "done"      # 預設值，向後相容既有資料
    assert m.relevant is True


def test_searchrun_area_and_next_page():
    from job_tracker.schemas import ResumeTarget, SearchRun
    run = SearchRun(search_id="s1", user="u1", keyword="python",
                    target=ResumeTarget(target_title="後端", resume_text="x"))
    assert run.area is None
    assert run.next_page == 1
    assert run.count == 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: FAIL（`JobMatch(job=job)` 缺 score 必填 / 無 status）

- [ ] **Step 3: 改 schema**

`JobMatch` 改為：

```python
class JobMatch(BaseModel):
    """職缺契合度分析。candidate/pending 階段尚無分數，用 status 區分。"""

    job: Job
    score: float = Field(default=0.0, ge=0, le=100, description="契合度 0~100")
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    requires_external_apply: bool = False
    cover_letter: str | None = None
    # candidate=爬到待選 / pending=排隊分析 / done=完成 / failed=失敗
    status: str = "done"
    relevant: bool = True  # 關鍵字是否命中（廣告→False，前端預設勾選用）
```

`SearchRun` 把 `next_offset` 改為 `next_page`：

```python
class SearchRun(BaseModel):
    search_id: str
    user: str
    keyword: str
    target: ResumeTarget
    area: str | None = None  # 縣市代碼，逗號分隔多選；None=全台
    created_at: datetime = Field(default_factory=_utcnow)
    next_page: int = 1       # 已爬到第幾頁，爬下一頁用
    count: int = 0           # 候選總數
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: PASS。注意：其他依賴 `next_offset` 的測試/程式（repository、jobs router）會在後續 task 改；本 task 只跑 `test_schemas.py`。

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/tests/test_schemas.py
git commit -m "feat(schema): JobMatch 加 status/relevant 與 optional 分數；SearchRun 加 area/next_page"
```

---

## Task 2: crawler — area 參數 + relevant 標記

**Files:**
- Modify: `backend/src/job_tracker/crawler/__init__.py`
- Test: `backend/tests/test_crawler.py`

**Interfaces:**
- Produces: `crawl_jobs(keyword, *, page=1, area=None, client=None) -> list[tuple[Job, bool]]`（(job, relevant)）；`_is_relevant(raw:dict, keyword:str) -> bool`

- [ ] **Step 1: 看現有 crawler 測試**

先 Read `backend/tests/test_crawler.py` 了解既有 MockTransport fixture 與 `parse_jobs` 測試形態（既有測試呼叫 `parse_jobs(payload)` 回 `list[Job]`，本 task 改回傳型別後需一併更新這些斷言）。

- [ ] **Step 2: 寫失敗測試**

新增（並調整既有 parse_jobs 斷言為 tuple）：

```python
def test_is_relevant_by_snippet_hit():
    from job_tracker.crawler import _is_relevant
    raw = {"jobName": "工程師", "descSnippet": "會 [[[Python]]] 尤佳", "description": ""}
    assert _is_relevant(raw, "python") is True


def test_is_relevant_by_literal():
    from job_tracker.crawler import _is_relevant
    raw = {"jobName": "Python 後端", "descSnippet": "", "description": ""}
    assert _is_relevant(raw, "python") is True


def test_not_relevant_is_ad():
    from job_tracker.crawler import _is_relevant
    raw = {"jobName": "房仲業務", "jobNameSnippet": "房仲業務",
           "descSnippet": "誠徵房仲", "description": "不動產銷售"}
    assert _is_relevant(raw, "python") is False
```

並為 `crawl_jobs` 的 area 帶入加一個測試（用 MockTransport 攔截 request，斷言 `request.url.params["area"]` 等於傳入值）：

```python
import httpx
import pytest
from job_tracker.crawler import crawl_jobs


@pytest.mark.asyncio
async def test_crawl_jobs_passes_area_and_returns_relevance():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["area"] = request.url.params.get("area")
        return httpx.Response(200, json={"data": [
            {"jobNo": "1", "jobName": "Python 工程師", "custName": "A",
             "link": {"job": "https://www.104.com.tw/job/abc"},
             "descSnippet": "[[[Python]]]", "salaryLow": 0, "salaryHigh": 0},
            {"jobNo": "2", "jobName": "房仲業務", "custName": "B",
             "link": {"job": "https://www.104.com.tw/job/xyz"},
             "descSnippet": "誠徵房仲", "description": "不動產", "salaryLow": 0, "salaryHigh": 0},
        ]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    out = await crawl_jobs("python", page=1, area="6001001000", client=client)
    await client.aclose()
    assert captured["area"] == "6001001000"
    assert [(j.job_id, rel) for j, rel in out] == [("1", True), ("2", False)]
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_crawler.py -v`
Expected: FAIL（`_is_relevant` 不存在 / `crawl_jobs` 無 area / 回傳非 tuple）

- [ ] **Step 4: 實作**

`crawl_jobs` 加 `area` 參數（None 不帶）：

```python
async def crawl_jobs(
    keyword: str,
    *,
    page: int = 1,
    area: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> list[tuple[Job, bool]]:
    params = {
        "ro": 0, "keyword": keyword, "order": 15, "asc": 0,
        "page": page, "mode": "s", "jobsource": "index_s",
    }
    if area:
        params["area"] = area
    owns_client = client is None
    client = client or httpx.AsyncClient()
    try:
        resp = await client.get(SEARCH_URL, params=params, headers=_HEADERS)
        resp.raise_for_status()
        payload = resp.json()
        out = [
            (_parse_job(raw), _is_relevant(raw, keyword))
            for raw in payload.get("data", [])
        ]
        logger.info("crawl keyword=%r page=%d area=%s -> %d jobs",
                    keyword, page, area, len(out))
        return out
    finally:
        if owns_client:
            await client.aclose()
```

新增 `_is_relevant`：

```python
def _is_relevant(raw: dict, keyword: str) -> bool:
    """104 會把與關鍵字無關的廣告職缺混入結果。命中關鍵字者 104 會在 snippet
    標 [[[關鍵字]]]；否則退而求其次看關鍵字 token 是否字面出現。"""
    snip = (raw.get("jobNameSnippet", "") or "") + (raw.get("descSnippet", "") or "")
    if "[[[" in snip:
        return True
    tokens = [t for t in keyword.lower().split() if t]
    if not tokens:
        return True
    hay = ((raw.get("jobName", "") or "") + " " + (raw.get("description", "") or "")).lower()
    return any(t in hay for t in tokens)
```

`parse_jobs`（若仍被既有測試引用）：保留回 `list[Job]` 供相容，或更新既有測試改用 `crawl_jobs`。實作者依 Step 1 所見決定，但 `crawl_jobs` 必須回 `list[tuple[Job, bool]]`。

- [ ] **Step 5: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_crawler.py -v`
Expected: PASS。
**範圍界線**：`services/analyze.py` 仍用舊 `crawl_jobs`（list[Job]）→ analyze 相關測試此時會壞，Task 5 修。本 task 只需 `tests/test_crawler.py` 綠。

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/crawler/__init__.py backend/tests/test_crawler.py
git commit -m "feat(crawler): crawl_jobs 加 area 篩選與 relevant 命中標記"
```

---

## Task 3: MatchRepository — candidate / status 方法

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`
- Test: `backend/tests/test_job_repository.py`

**Interfaces:**
- Produces（`MatchRepository` 新增）：
  - `add_candidate(search_id, user, job:Job, relevant:bool) -> None`（存 status="candidate" placeholder；已存在則不覆蓋）
  - `set_pending(search_id, job_ids:list[str]) -> None`（批次標 pending）
  - `set_result(search_id, job_id, analysis:JobMatch) -> None`（更新 score/reasons/gaps/requires_external_apply、status="done"）
  - `set_failed(search_id, job_id) -> None`（status="failed"）
  - 既有 `set_match`/`list_by_search`/`get_match`/`set_cover_letter` 保留

- [ ] **Step 1: 寫失敗測試**（append 到 `test_job_repository.py`）

```python
async def test_add_candidate_and_status_flow(match_repo: MatchRepository):
    from job_tracker.schemas import JobMatch
    job = make_job("1", "c1")
    await match_repo.add_candidate("s1", "u1", job, relevant=True)
    m = await match_repo.get_match("s1", "1")
    assert m.status == "candidate" and m.relevant is True and m.score == 0

    await match_repo.set_pending("s1", ["1"])
    assert (await match_repo.get_match("s1", "1")).status == "pending"

    analysis = JobMatch(job=job, score=88, reasons=["r"], gaps=["g"],
                        requires_external_apply=True)
    await match_repo.set_result("s1", "1", analysis)
    done = await match_repo.get_match("s1", "1")
    assert done.status == "done" and done.score == 88
    assert done.requires_external_apply is True


async def test_add_candidate_is_idempotent(match_repo: MatchRepository):
    job = make_job("1", "c1")
    await match_repo.add_candidate("s1", "u1", job, relevant=True)
    await match_repo.add_candidate("s1", "u1", job, relevant=False)  # 不覆蓋
    assert (await match_repo.get_match("s1", "1")).relevant is True


async def test_set_failed(match_repo: MatchRepository):
    job = make_job("1", "c1")
    await match_repo.add_candidate("s1", "u1", job, relevant=True)
    await match_repo.set_failed("s1", "1")
    assert (await match_repo.get_match("s1", "1")).status == "failed"
```

（`make_job` 已存在於該檔。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_job_repository.py -v`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 實作**（`MatchRepository` 內新增）

```python
    async def add_candidate(self, search_id, user, job, relevant) -> None:
        _id = f"{search_id}|{job.job_id}"
        if await self._col.find_one({"_id": _id}):
            return  # 已存在不覆蓋（重複爬到同職缺）
        doc = JobMatch(job=job, status="candidate", relevant=relevant).model_dump(mode="json")
        doc.update({"_id": _id, "search_id": search_id, "user": user, "job_id": job.job_id})
        await self._col.insert_one(doc)

    async def set_pending(self, search_id, job_ids) -> None:
        await self._col.update_many(
            {"search_id": search_id, "job_id": {"$in": list(job_ids)}},
            {"$set": {"status": "pending"}},
        )

    async def set_result(self, search_id, job_id, analysis) -> None:
        await self._col.update_one(
            {"_id": f"{search_id}|{job_id}"},
            {"$set": {
                "score": analysis.score,
                "reasons": analysis.reasons,
                "gaps": analysis.gaps,
                "requires_external_apply": analysis.requires_external_apply,
                "status": "done",
            }},
        )

    async def set_failed(self, search_id, job_id) -> None:
        await self._col.update_one(
            {"_id": f"{search_id}|{job_id}"}, {"$set": {"status": "failed"}}
        )
```

（`JobMatch` 已在該檔 import。）

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_job_repository.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_job_repository.py
git commit -m "feat(repo): MatchRepository 候選 placeholder 與 status 轉換"
```

---

## Task 4: SearchRepository — area + next_page

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`
- Test: `backend/tests/test_search_repository.py`

**Interfaces:**
- Produces：`create(user, keyword, target, area=None) -> SearchRun`；`advance_page(search_id, next_page, count_delta) -> None`（取代舊 `advance`）

- [ ] **Step 1: 改寫測試**（把舊 `test_advance_updates_offset_and_count` 換掉）

```python
async def test_create_with_area(db):
    repo = SearchRepository(db)
    run = await repo.create("u1", "python", _target(), area="6001001000")
    assert (await repo.get(run.search_id)).area == "6001001000"


async def test_advance_page(db):
    repo = SearchRepository(db)
    run = await repo.create("u1", "python", _target())
    await repo.advance_page(run.search_id, next_page=2, count_delta=30)
    await repo.advance_page(run.search_id, next_page=3, count_delta=28)
    got = await repo.get(run.search_id)
    assert got.next_page == 3
    assert got.count == 58
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_search_repository.py -v`
Expected: FAIL（`create` 無 area / 無 `advance_page`）

- [ ] **Step 3: 實作**

```python
    async def create(self, user, keyword, target, area=None) -> SearchRun:
        run = SearchRun(search_id=uuid4().hex, user=user, keyword=keyword,
                        target=target, area=area)
        doc = run.model_dump(mode="json")
        doc["_id"] = run.search_id
        await self._col.insert_one(doc)
        return run

    async def advance_page(self, search_id, next_page, count_delta) -> None:
        await self._col.update_one(
            {"_id": search_id},
            {"$set": {"next_page": next_page}, "$inc": {"count": count_delta}},
        )
```

移除舊 `advance`。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_search_repository.py -v`
Expected: PASS（cascade 測試等其餘仍綠）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_search_repository.py
git commit -m "feat(repo): SearchRepository 支援 area 與 next_page 翻頁"
```

---

## Task 5: analyze service 拆分 + 可注入 runner + 全域 semaphore

**Files:**
- Modify: `backend/src/job_tracker/services/analyze.py`
- Test: `backend/tests/test_analyze.py`（改寫）

**Interfaces:**
- Produces:
  - `crawl_candidates(search_id, user, keyword, area, page, job_repo, match_repo, *, http_client=None) -> list[JobMatch]`（爬一頁、`add_candidate`、回該頁候選）
  - `analyze_one(search_id, user, job_id, target, job_repo, match_repo, quota, *, http_client=None, llm_client=None) -> None`（抓詳情經 semaphore → LLM → `set_result`/`set_failed`；done 後 `quota.add(user,1)`）
  - `AnalysisRunner` Protocol（`submit(coros: list[Awaitable]) -> None`）；`AsyncioRunner`（預設，`asyncio.create_task` 逐筆序列）
  - module-level `DETAIL_SEMAPHORE = asyncio.Semaphore(2)`

- [ ] **Step 1: 寫失敗測試**（改寫 `test_analyze.py`，用 MockTransport + 假 llm）

```python
import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.schemas import Job, JobMatch, ResumeTarget
from job_tracker.services import analyze as analyze_svc


def _target():
    return ResumeTarget(target_title="後端", resume_text="Python")


def _search_html_resp():
    return httpx.Response(200, json={"data": [
        {"jobNo": "1", "jobName": "Python 工程師", "custName": "A",
         "link": {"job": "https://www.104.com.tw/job/abc"},
         "descSnippet": "[[[Python]]]", "salaryLow": 0, "salaryHigh": 0},
    ]})


def _detail_resp():
    return httpx.Response(200, json={"data": {
        "jobDetail": {"jobDescription": "JD", "salary": "月薪50,000元", "addressRegion": "台北"},
        "condition": {"workExp": "3年", "edu": "大學", "major": [], "specialty": []},
    }})


async def test_crawl_candidates_stores_candidates():
    db = AsyncMongoMockClient()["test"]
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _search_html_resp()))
    out = await analyze_svc.crawl_candidates(
        "s1", "u1", "python", None, 1, JobRepository(db), MatchRepository(db),
        http_client=client)
    await client.aclose()
    assert [m.job.job_id for m in out] == ["1"]
    stored = await MatchRepository(db).get_match("s1", "1")
    assert stored.status == "candidate" and stored.relevant is True


async def test_analyze_one_done_and_quota(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    mr, jr, qr = MatchRepository(db), JobRepository(db), QuotaRepository(db)
    job = Job(job_id="1", code="abc", title="t", company="co", url="https://x/abc")
    await mr.add_candidate("s1", "u1", job, relevant=True)

    async def fake_match(target, job, detail, client=None):
        return JobMatch(job=job, score=77, reasons=["r"], gaps=["g"])
    monkeypatch.setattr(analyze_svc.job_matching, "analyze", fake_match)

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _detail_resp()))
    await analyze_svc.analyze_one("s1", "u1", "1", _target(), jr, mr, qr,
                                  http_client=client)
    await client.aclose()
    done = await mr.get_match("s1", "1")
    assert done.status == "done" and done.score == 77
    assert await qr.used_today("u1") == 1


async def test_analyze_one_failure_marks_failed(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    mr, jr, qr = MatchRepository(db), JobRepository(db), QuotaRepository(db)
    job = Job(job_id="1", code="abc", title="t", company="co", url="https://x/abc")
    await mr.add_candidate("s1", "u1", job, relevant=True)

    def boom(r): raise httpx.ConnectError("fail")
    client = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    await analyze_svc.analyze_one("s1", "u1", "1", _target(), jr, mr, qr,
                                  http_client=client)
    await client.aclose()
    assert (await mr.get_match("s1", "1")).status == "failed"
    assert await qr.used_today("u1") == 0  # 失敗不計額度
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_analyze.py -v`
Expected: FAIL（`crawl_candidates`/`analyze_one` 不存在）

- [ ] **Step 3: 實作**（重寫 `analyze.py`）

```python
"""職缺契合度流程（兩階段、非同步逐筆）。

爬取：crawl_candidates 抓 104 一頁、存 candidate placeholder。
分析：analyze_one 對單筆抓詳情（經全域 semaphore 節流）→ LLM → 寫結果。
背景執行用可注入的 AnalysisRunner（預設 asyncio.create_task 逐筆序列）。
"""

import asyncio
import logging
from typing import Awaitable, Protocol

import httpx

from job_tracker.crawler import crawl_jobs, fetch_job_detail
from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository,
)
from job_tracker.schemas import JobMatch, ResumeTarget
from job_tracker.services import job_matching

logger = logging.getLogger(__name__)

# 全域：限制同時對 104 詳情 API 的併發，避免多背景任務一起打被鎖
DETAIL_SEMAPHORE = asyncio.Semaphore(2)


async def crawl_candidates(
    search_id: str, user: str, keyword: str, area: str | None, page: int,
    job_repo: JobRepository, match_repo: MatchRepository,
    *, http_client: httpx.AsyncClient | None = None,
) -> list[JobMatch]:
    owns = http_client is None
    http_client = http_client or httpx.AsyncClient()
    try:
        pairs = await crawl_jobs(keyword, page=page, area=area, client=http_client)
        for job, relevant in pairs:
            await match_repo.add_candidate(search_id, user, job, relevant)
        logger.info("crawl_candidates s=%s page=%d -> %d", search_id, page, len(pairs))
        return [await match_repo.get_match(search_id, j.job_id) for j, _ in pairs]
    finally:
        if owns:
            await http_client.aclose()


async def analyze_one(
    search_id: str, user: str, job_id: str, target: ResumeTarget,
    job_repo: JobRepository, match_repo: MatchRepository, quota: QuotaRepository,
    *, http_client: httpx.AsyncClient | None = None, llm_client=None,
) -> None:
    owns = http_client is None
    http_client = http_client or httpx.AsyncClient()
    try:
        cand = await match_repo.get_match(search_id, job_id)
        if cand is None:
            return
        job = cand.job
        async with DETAIL_SEMAPHORE:
            detail = await fetch_job_detail(job.code, client=http_client)
        if detail.salary:
            job.salary = detail.salary
        await job_repo.upsert_job(job)
        await job_repo.set_detail(job_id, detail)
        analysis = await job_matching.analyze(target, job, detail, client=llm_client)
        await match_repo.set_result(search_id, job_id, analysis)
        await quota.add(user, 1)  # 每筆 done 才計額度
    except Exception:
        logger.warning("分析失敗 job=%s", job_id, exc_info=True)
        await match_repo.set_failed(search_id, job_id)
    finally:
        if owns:
            await http_client.aclose()


class AnalysisRunner(Protocol):
    def submit(self, coros: list[Awaitable]) -> None: ...


class AsyncioRunner:
    """預設 runner：背景逐筆序列跑（彼此間靠各自節流 + 全域 semaphore 護 104）。"""

    def submit(self, coros: list[Awaitable]) -> None:
        async def _run_all():
            for c in coros:
                await c
        asyncio.create_task(_run_all())
```

注意：`fetch_job_detail` 本身不含逐筆間隔；逐筆序列由 `_run_all` 依序 await 達成，外加 `DETAIL_SEMAPHORE` 限制跨任務併發。若要保留 2–5 秒隨機間隔，在 `_run_all` 每筆之間 `await asyncio.sleep(random.uniform(2,5))`（import random）。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_analyze.py -v`
Expected: PASS
**範圍界線**：`api/routers/jobs.py` 仍用舊 `analyze_jobs`（已不存在）→ jobs API 測試此時壞，Task 6 修。

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/services/analyze.py backend/tests/test_analyze.py
git commit -m "feat(analyze): 拆兩階段 crawl_candidates/analyze_one + 可注入 runner + semaphore"
```

---

## Task 6: deps + jobs router 兩階段端點

**Files:**
- Modify: `backend/src/job_tracker/api/deps.py`
- Modify: `backend/src/job_tracker/api/routers/jobs.py`
- Test: `backend/tests/test_jobs_api.py`（改寫）

**Interfaces:**
- Produces（deps）：`get_analysis_runner() -> AnalysisRunner`（回 module 級單例 `AsyncioRunner`）
- Produces（端點 `/jobs`）：
  - `POST /searches` body `{keyword, target, area?}` → `{search_id, candidates}`
  - `POST /searches/{id}/crawl-next` → `{candidates}`
  - `POST /searches/{id}/analyze` body `{job_ids}` → `{queued}`（429 if 額度不足）
  - `GET /searches/{id}/matches`、`GET /searches`、`DELETE /searches/{id}`、`POST /searches/{id}/cover-letter` 維持；移除 `/next`

- [ ] **Step 1: deps 加 runner provider**

```python
from job_tracker.services.analyze import AnalysisRunner, AsyncioRunner

_runner = AsyncioRunner()

def get_analysis_runner() -> AnalysisRunner:
    return _runner
```
`__all__` 補 `"get_analysis_runner"`。

- [ ] **Step 2: 寫失敗測試**（改寫 `test_jobs_api.py`，注入同步 runner）

```python
import asyncio
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import jobs as jobs_router
from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.main import app
from job_tracker.schemas import Job


class SyncRunner:
    """測試用：收集 coros，立即在當前 loop 跑完。"""
    def submit(self, coros):
        async def _run():
            for c in coros:
                await c
        # TestClient 在獨立 thread 跑 event loop；用 asyncio.run 安全執行
        asyncio.run(_run())


_PAYLOAD = {"keyword": "python",
            "target": {"target_title": "後端", "expected_salary": 70000, "resume_text": "Python"}}


def _wire(db, monkeypatch, candidates):
    async def fake_crawl(search_id, user, keyword, area, page, job_repo, match_repo, **kw):
        for jid, rel in candidates:
            job = Job(job_id=jid, code=f"c{jid}", title="t", company="co", url=f"https://x/c{jid}")
            await match_repo.add_candidate(search_id, user, job, rel)
        return [await match_repo.get_match(search_id, jid) for jid, _ in candidates]

    async def fake_analyze_one(search_id, user, job_id, target, job_repo, match_repo, quota, **kw):
        from job_tracker.schemas import JobMatch
        m = await match_repo.get_match(search_id, job_id)
        await match_repo.set_result(search_id, job_id,
                                    JobMatch(job=m.job, score=88, reasons=["r"], gaps=["g"]))
        await quota.add(user, 1)

    monkeypatch.setattr(jobs_router, "crawl_candidates", fake_crawl)
    monkeypatch.setattr(jobs_router, "analyze_one", fake_analyze_one)
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    app.dependency_overrides[deps.get_analysis_runner] = lambda: SyncRunner()


def test_search_returns_candidates(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True), ("2", False)])
    try:
        body = TestClient(app).post("/api/jobs/searches", json=_PAYLOAD).json()
    finally:
        app.dependency_overrides.clear()
    assert body["search_id"]
    assert [(c["job_id"], c["relevant"]) for c in body["candidates"]] == [("1", True), ("2", False)]
    # 不計額度
    assert asyncio.run(QuotaRepository(db).used_today("dev@local")) == 0


def test_analyze_selected_runs_and_counts_quota(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True), ("2", True)])
    try:
        client = TestClient(app)
        sid = client.post("/api/jobs/searches", json=_PAYLOAD).json()["search_id"]
        resp = client.post(f"/api/jobs/searches/{sid}/analyze", json={"job_ids": ["1"]})
        matches = client.get(f"/api/jobs/searches/{sid}/matches").json()
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["queued"] == 1
    done = [m for m in matches if m["status"] == "done"]
    assert [m["job"]["job_id"] for m in done] == ["1"] and done[0]["score"] == 88
    assert asyncio.run(QuotaRepository(db).used_today("dev@local")) == 1


def test_analyze_over_quota_is_429(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    _wire(db, monkeypatch, [("1", True)])
    asyncio.run(QuotaRepository(db).add("dev@local", 50))  # 已用滿（預設上限 50）
    try:
        client = TestClient(app)
        sid = client.post("/api/jobs/searches", json=_PAYLOAD).json()["search_id"]
        resp = client.post(f"/api/jobs/searches/{sid}/analyze", json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 429
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_jobs_api.py -v`
Expected: FAIL（端點未改）

- [ ] **Step 4: 改寫 jobs router**

```python
"""職缺端點：兩階段（爬候選 → 勾選 → 非同步逐筆分析）+ 求職信。需登入。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user, ensure_quota, get_analysis_runner, get_job_repo,
    get_match_repo, get_quota_repo, get_search_repo,
)
from job_tracker.config import get_settings
from job_tracker.db.repositories import (
    JobRepository, MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.schemas import JobMatch, ResumeTarget, SearchRun
from job_tracker.services import cover_letter as cover_letter_svc
from job_tracker.services.analyze import (
    AnalysisRunner, analyze_one, crawl_candidates,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class CreateSearchRequest(BaseModel):
    keyword: str
    target: ResumeTarget
    area: str | None = None


class AnalyzeRequest(BaseModel):
    job_ids: list[str]


class CoverLetterRequest(BaseModel):
    job_id: str


async def _ensure_owned(search_id, user, search_repo) -> SearchRun:
    run = await search_repo.get(search_id)
    if run is None or run.user != user:
        raise HTTPException(status_code=404, detail="找不到該搜尋紀錄")
    return run


@router.post("/searches")
async def create_search(
    req: CreateSearchRequest,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> dict:
    run = await search_repo.create(user, req.keyword, req.target, area=req.area)
    cands = await crawl_candidates(run.search_id, user, req.keyword, req.area, 1,
                                   job_repo, match_repo)
    await search_repo.advance_page(run.search_id, next_page=2, count_delta=len(cands))
    return {"search_id": run.search_id, "candidates": [c.model_dump(mode="json") for c in cands]}


@router.post("/searches/{search_id}/crawl-next")
async def crawl_next(
    search_id: str,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> dict:
    run = await _ensure_owned(search_id, user, search_repo)
    cands = await crawl_candidates(search_id, user, run.keyword, run.area, run.next_page,
                                   job_repo, match_repo)
    await search_repo.advance_page(search_id, next_page=run.next_page + 1, count_delta=len(cands))
    return {"candidates": [c.model_dump(mode="json") for c in cands]}


@router.post("/searches/{search_id}/analyze")
async def analyze_selected(
    search_id: str,
    req: AnalyzeRequest,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
    runner: AnalysisRunner = Depends(get_analysis_runner),
) -> dict:
    run = await _ensure_owned(search_id, user, search_repo)
    # 驗證 job_ids 都屬於該 search 的候選
    valid = []
    for jid in req.job_ids:
        m = await match_repo.get_match(search_id, jid)
        if m is not None:
            valid.append(jid)
    if not valid:
        raise HTTPException(status_code=400, detail="沒有可分析的職缺")
    # 額度檢查（剩餘 ≥ 選中數）
    limit = get_settings().daily_call_limit
    if await quota.used_today(user) + len(valid) > limit:
        raise HTTPException(status_code=429, detail=f"今日額度不足（每日 {limit} 次）")
    await match_repo.set_pending(search_id, valid)
    coros = [analyze_one(search_id, user, jid, run.target, job_repo, match_repo, quota)
             for jid in valid]
    runner.submit(coros)
    return {"queued": len(valid)}


@router.get("/searches/{search_id}/matches")
async def search_matches(
    search_id: str,
    user: str = Depends(current_user),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[JobMatch]:
    await _ensure_owned(search_id, user, search_repo)
    return await match_repo.list_by_search(search_id)


@router.get("/searches")
async def list_searches(
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[SearchRun]:
    return await search_repo.list(user)


@router.delete("/searches/{search_id}")
async def delete_search(
    search_id: str,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> dict:
    await _ensure_owned(search_id, user, search_repo)
    await search_repo.delete(search_id)
    return {"ok": True}


@router.post("/searches/{search_id}/cover-letter")
async def generate_cover_letter(
    search_id: str,
    req: CoverLetterRequest,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> dict[str, str]:
    run = await _ensure_owned(search_id, user, search_repo)
    match = await match_repo.get_match(search_id, req.job_id)
    if match is None:
        raise HTTPException(status_code=404, detail="找不到該職缺分析")
    await ensure_quota(user, quota)
    detail = await job_repo.get_detail(req.job_id)
    text = await cover_letter_svc.generate(run.target, match.job, detail)
    await match_repo.set_cover_letter(search_id, req.job_id, text)
    await quota.add(user, 1)
    return {"cover_letter": text}
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd backend && uv run pytest -v`
Expected: 全綠（本 task 是後端最後一塊）。若 `test_applications_api.py` 等仍引用舊行為，調整。

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/api/deps.py backend/src/job_tracker/api/routers/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat(api): jobs router 兩階段端點（爬候選/分析選中/非同步 runner）"
```

---

## Task 7: 前端 types + client + 縣市表

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/constants/regions.ts`

**Interfaces:**
- Produces（types）：`JobMatch` 加 `status`、`relevant`；`SearchRun` 加 `area`、`next_page`（移除 `next_offset`）
- Produces（client）：`createSearch({keyword,target,area?})` → `{search_id, candidates: JobMatch[]}`；`crawlNext(id)` → `{candidates}`；`analyzeSelected(id, job_ids)` → `{queued}`；`searchMatches`/`listSearches`/`deleteSearch`/`coverLetter`/applications 維持
- Produces：`REGIONS`（縣市↔代碼）

- [ ] **Step 1: types**

`JobMatch` 加 `status: "candidate"|"pending"|"done"|"failed"` 與 `relevant: boolean`；`SearchRun` 把 `next_offset` 改 `next_page`、加 `area: string | null`。

- [ ] **Step 2: client**

```typescript
  createSearch: (req: { keyword: string; target: ResumeTarget; area?: string | null }) =>
    request<{ search_id: string; candidates: JobMatch[] }>("/jobs/searches", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  crawlNext: (searchId: string) =>
    request<{ candidates: JobMatch[] }>(`/jobs/searches/${searchId}/crawl-next`, { method: "POST" }),
  analyzeSelected: (searchId: string, jobIds: string[]) =>
    request<{ queued: number }>(`/jobs/searches/${searchId}/analyze`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_ids: jobIds }),
    }),
```
移除舊 `nextBatch`。其餘維持。

- [ ] **Step 3: 縣市表**

```typescript
// frontend/src/constants/regions.ts
// 104 地區代碼（6001 + 縣市序號 + 000）。已驗證：台北 6001001000、新竹市 6001006000。
export const REGIONS: { value: string; label: string }[] = [
  { value: "6001001000", label: "台北市" },
  { value: "6001002000", label: "新北市" },
  { value: "6001003000", label: "基隆市" },
  { value: "6001004000", label: "宜蘭縣" },
  { value: "6001005000", label: "桃園市" },
  { value: "6001006000", label: "新竹市" },
  { value: "6001007000", label: "新竹縣" },
  { value: "6001008000", label: "苗栗縣" },
  { value: "6001009000", label: "台中市" },
  { value: "6001010000", label: "彰化縣" },
  { value: "6001011000", label: "南投縣" },
  { value: "6001012000", label: "雲林縣" },
  { value: "6001013000", label: "嘉義市" },
  { value: "6001014000", label: "嘉義縣" },
  { value: "6001015000", label: "台南市" },
  { value: "6001016000", label: "高雄市" },
  { value: "6001017000", label: "屏東縣" },
  { value: "6001018000", label: "台東縣" },
  { value: "6001019000", label: "花蓮縣" },
  { value: "6001020000", label: "澎湖縣" },
  { value: "6001021000", label: "金門縣" },
  { value: "6001022000", label: "連江縣" },
];
```

實作者：用後端 `crawl_jobs` 或 curl 抽驗 2–3 個中段縣市（如台中 `6001009000`、台南 `6001015000`）確認 jobAddrNo 前綴吻合；若代碼有出入，依實測修正。

- [ ] **Step 4: 建置驗證**

Run: `cd frontend && npx tsc -b`
Expected: 錯誤僅來自 `JobList.tsx`（Task 8 修）；types/client/regions 自身無誤。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts frontend/src/constants/regions.ts
git commit -m "feat(fe): 兩階段 API client、status/relevant 型別、縣市代碼表"
```

---

## Task 8: 前端 JobList — 候選勾選 + 縣市 + 輪詢

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`

**Interfaces:**
- Consumes: `api.createSearch/crawlNext/analyzeSelected/searchMatches/listSearches/deleteSearch`、`REGIONS`

- [ ] **Step 1: 讀現有 JobList**

先 Read `frontend/src/pages/JobList.tsx`，保留 MatchCard（求職信、加入追蹤）。本 task 重構主體為「候選勾選 + 輪詢」。

- [ ] **Step 2: 主體改造**

關鍵狀態與資料流：

```tsx
export function JobList() {
  const { target } = useResume();
  const [keyword, setKeyword] = useState("");
  const [area, setArea] = useState<string[]>([]);     // 縣市多選
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set()); // 勾選的候選 job_id
  const qc = useQueryClient();

  const searchesQ = useQuery({ queryKey: ["searches"], queryFn: api.listSearches });

  const matchesQ = useQuery({
    queryKey: ["search-matches", selectedId],
    queryFn: () => api.searchMatches(selectedId!),
    enabled: !!selectedId,
    refetchInterval: (q) =>
      (q.state.data ?? []).some((m) => m.status === "pending") ? 2500 : false,
  });
  const matches = matchesQ.data ?? [];
  const candidates = matches.filter((m) => m.status === "candidate");
  const results = matches.filter((m) => m.status !== "candidate");

  const createMut = useMutation({
    mutationFn: api.createSearch,
    onSuccess: (data) => {
      setSelectedId(data.search_id);
      // 預設勾選命中關鍵字（relevant）的候選
      setPicked(new Set(data.candidates.filter((c) => c.relevant).map((c) => c.job.job_id)));
      qc.invalidateQueries({ queryKey: ["searches"] });
      qc.invalidateQueries({ queryKey: ["search-matches", data.search_id] });
    },
  });
  const crawlMut = useMutation({
    mutationFn: () => api.crawlNext(selectedId!),
    onSuccess: (data) => {
      setPicked((p) => {
        const n = new Set(p);
        data.candidates.filter((c) => c.relevant).forEach((c) => n.add(c.job.job_id));
        return n;
      });
      qc.invalidateQueries({ queryKey: ["search-matches", selectedId] });
    },
  });
  const analyzeMut = useMutation({
    mutationFn: () => api.analyzeSelected(selectedId!, [...picked]),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["search-matches", selectedId] }),
  });

  const toggle = (id: string) =>
    setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  // 只在「還是候選」的職缺裡算可分析數（已分析的不重複送）
  const pickedCandidates = candidates.filter((c) => picked.has(c.job.job_id));
```

控制列：關鍵字 `TextInput` + 縣市 `MultiSelect`（`data={REGIONS}` `value={area}` `onChange={setArea}` 可清空）+「爬取」鈕（`onClick`: `createMut.mutate({ keyword, target, area: area.join(",") || null })`）。

- [ ] **Step 3: 候選清單 + 分析按鈕**

候選區（在歷史 chips 之後、結果之前）：每筆一列 `Checkbox`（`checked={picked.has(id)}` `onChange={() => toggle(id)}`）+ 職稱連結 + 公司 + 薪資 + 廣告標記（`!relevant` 顯示灰色「廣告？」chip）。底部「分析選中（{pickedCandidates.length} 筆）」鈕 → `analyzeMut.mutate()`，`disabled` 當 `pickedCandidates.length===0 || analyzeMut.isPending`。「爬下一頁」→ `crawlMut.mutate()`。

- [ ] **Step 4: 結果區依 status 渲染**

`results` 依 status：
- `pending`：簡單轉圈卡（公司·職稱 + Loader「分析中…」）
- `done`：現有 `<MatchCard match={m} searchId={selectedId!} />`
- `failed`：錯誤卡 + 「重試」鈕（`api.analyzeSelected(selectedId!, [m.job.job_id])` 後 invalidate）

排序：done 依 score 由高到低（`list_by_search` 已排，但混了 pending/failed；前端可再 `results.sort` 把 done 依 score、pending/failed 置頂或置底，擇一，實作時定）。

- [ ] **Step 5: 建置驗證**

Run: `cd frontend && npm run build`
Expected: build 成功。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(fe): JobList 候選勾選 + 縣市篩選 + 非同步輪詢逐筆顯示"
```

---

## Task 9: 端對端煙霧 + 文件

**Files:**
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: 後端全測試**

Run: `cd backend && uv run pytest -v` → 全綠。

- [ ] **Step 2: 啟動服務手動/Playwright 煙霧驗證**

殺 8000/5173 殘留後啟動，驗證：選縣市 + 關鍵字 → 爬取出候選清單（廣告未勾）→ 勾選 → 分析 → 輪詢逐筆從 pending 變 done → 生成求職信 → 加入追蹤。實際爬 104 慢，可只驗 1–2 筆。

- [ ] **Step 3: 更新 PROGRESS.md**

記錄兩階段流程 + 非同步分析 + 選地區完成；**保留兩個已知限制**（額度可能超賣、背景任務不持久化）於文件。

- [ ] **Step 4: Commit**

```bash
git add docs/PROGRESS.md
git commit -m "docs: 更新進度（候選勾選 + 非同步分析 + 選地區）"
```

---

## Self-Review 註記

- **Spec 覆蓋**：兩階段（T2 crawler relevant/area、T5 crawl_candidates、T6 端點）、候選 placeholder（T3）、非同步 runner + semaphore（T5）、額度檢查+逐筆計（T6）、選地區（T2/T4/T6/T7）、前端勾選+輪詢（T8）皆有對應 task。
- **已知限制**：額度超賣、背景不持久化 → 寫進 Global Constraints 與 T9 文件，程式碼註解保留。
- **型別一致**：`crawl_jobs -> list[tuple[Job,bool]]`、`crawl_candidates`/`analyze_one`/`AnalysisRunner.submit(coros)`、`add_candidate`/`set_pending`/`set_result`/`set_failed`、`advance_page`、端點 `{candidates}`/`{queued}` 跨 task 統一。
- **範圍界線**：T2/T5 完成後 analyze/jobs 暫時壞屬預期，T5/T6 修復；T6 為後端最後一塊應全綠。
