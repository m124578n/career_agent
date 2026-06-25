# 本機爬蟲 agent 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「打 104」這一步從雲端搬到家用住宅 IP 的本機 agent，繞過 104 對機房 IP 的封鎖；雲端用 MongoDB 任務隊列派工，agent 輪詢認領、抓取、回填原始 JSON，解析/LLM 留雲端。

**Architecture:** 雲端後端把「搜尋」「詳情」兩種 104 請求 enqueue 進 MongoDB `crawl_tasks` collection。本機 agent（獨立小 Python script）帶共享密鑰輪詢 `/api/agent/claim` 原子認領任務 → 用住宅 IP 抓 104 → `POST /api/agent/complete` 回原始 JSON。雲端 complete 端點依任務型別解析（`parse_search_payload` / `parse_job_detail`），search 任務存候選、detail 任務跑 LLM 分析。agent 離線時任務排隊等待，前端以心跳判定在線/離線並顯示排隊狀態。

**Tech Stack:** FastAPI、MongoDB（motor / mongomock_motor 測試）、httpx、Pydantic、React + Mantine + TanStack Query。

## Global Constraints

- Python 後端用 uv；測試用 `uv run pytest`，既有 103 測試需保持全綠。
- 測試模式：`mongomock_motor.AsyncMongoMockClient`、`httpx.ASGITransport`、`app.dependency_overrides`、`monkeypatch`（見既有 `tests/test_jobs_api.py`）。conftest 已強制 dev 設定（`GOOGLE_CLIENT_ID=""`）。
- agent **不解析、不 import job_tracker 套件**：只抓 104 回原始 JSON。解析/LLM 全留雲端一處。
- agent ↔ 雲端認證用共享密鑰 `AGENT_SECRET`（`Authorization: Bearer <secret>`），與使用者 Google 登入分離。
- 既有時間戳模式：schemas 用 `datetime.now(UTC)`（`_utcnow`），存 DB 用 `model_dump(mode="json")`。
- 分支：開發在 `dev`，驗證 OK 才合 `main`（合 `main` 才觸發部署）。agent 本機跑、不經部署。
- 數值預設（本計畫採用）：agent 輪詢間隔 3 秒；detail 任務間節流 2–5 秒隨機；`pending` 過期 24h；`claimed` 逾時回收 5 分鐘；心跳判定離線 30 秒。

---

## 階段 A — 後端任務隊列核心

### Task 1: CrawlTask schema

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py`（在 `SearchRun` 後新增）
- Test: `backend/tests/test_schemas.py`（追加）

**Interfaces:**
- Produces: `CrawlTask` Pydantic model，欄位 `task_id:str, type:str, payload:dict, status:str="pending", search_id:str, user:str, job_id:str|None=None, raw_json:dict|None=None, error:str|None=None, created_at:datetime, claimed_at:datetime|None=None, completed_at:datetime|None=None`。

- [ ] **Step 1: 寫失敗測試**

在 `backend/tests/test_schemas.py` 追加：

```python
from job_tracker.schemas import CrawlTask


def test_crawl_task_defaults():
    t = CrawlTask(task_id="t1", type="search", payload={"keyword": "ai", "page": 1, "area": None},
                  search_id="s1", user="u@x")
    assert t.status == "pending"
    assert t.job_id is None
    assert t.raw_json is None
    assert t.created_at is not None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_schemas.py::test_crawl_task_defaults -v`
Expected: FAIL（`ImportError: cannot import name 'CrawlTask'`）

- [ ] **Step 3: 實作 schema**

在 `backend/src/job_tracker/schemas/__init__.py` 的 `SearchRun` 類別後新增：

```python
class CrawlTask(BaseModel):
    """一筆交給本機 agent 代打 104 的任務（search 或 detail）。"""

    task_id: str
    type: str  # "search" | "detail"
    payload: dict  # search: {keyword, page, area}; detail: {code}
    status: str = "pending"  # pending|claimed|done|failed|expired
    search_id: str
    user: str
    job_id: str | None = None  # detail 任務綁定的職缺
    raw_json: dict | None = None  # agent 回填的原始 104 JSON
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_schemas.py::test_crawl_task_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/tests/test_schemas.py
git commit -m "feat(be): CrawlTask schema（agent 任務隊列）"
```

---

### Task 2: CrawlTaskRepository — enqueue + 原子 claim

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`（檔末新增類別）
- Test: `backend/tests/test_crawl_queue.py`（新增）

**Interfaces:**
- Consumes: `CrawlTask`（Task 1）
- Produces: `CrawlTaskRepository(db)`，方法：
  - `async enqueue(task: CrawlTask) -> CrawlTask`
  - `async claim() -> CrawlTask | None`（原子 `find_one_and_update`，pending→claimed，設 `claimed_at`；無 pending 回 None）
  - `async get(task_id: str) -> CrawlTask | None`

- [ ] **Step 1: 寫失敗測試**

新增 `backend/tests/test_crawl_queue.py`：

```python
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import CrawlTaskRepository
from job_tracker.schemas import CrawlTask


def _task(task_id="t1", type="search"):
    return CrawlTask(task_id=task_id, type=type,
                     payload={"keyword": "ai", "page": 1, "area": None},
                     search_id="s1", user="u@x")


@pytest.mark.asyncio
async def test_enqueue_then_claim_returns_pending_task():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    claimed = await repo.claim()
    assert claimed is not None
    assert claimed.task_id == "t1"
    assert claimed.status == "claimed"
    assert claimed.claimed_at is not None


@pytest.mark.asyncio
async def test_claim_is_atomic_no_double_claim():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    first = await repo.claim()
    second = await repo.claim()  # 已無 pending
    assert first is not None and first.task_id == "t1"
    assert second is None


@pytest.mark.asyncio
async def test_claim_returns_none_when_empty():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    assert await repo.claim() is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -v`
Expected: FAIL（`ImportError: cannot import name 'CrawlTaskRepository'`）

- [ ] **Step 3: 實作 repository**

在 `backend/src/job_tracker/db/repositories.py` 檔末新增（檔頭 import 已有 `datetime, UTC`；確認 `CrawlTask` 在 `from job_tracker.schemas import (...)` 清單內，若無則加入）：

```python
class CrawlTaskRepository:
    """交給本機 agent 代打 104 的任務隊列。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["crawl_tasks"]

    async def enqueue(self, task: CrawlTask) -> CrawlTask:
        doc = task.model_dump(mode="json")
        doc["_id"] = task.task_id
        await self._col.insert_one(doc)
        return task

    async def claim(self) -> CrawlTask | None:
        """原子認領一個 pending 任務（pending→claimed）。多 agent 也安全。"""
        doc = await self._col.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "claimed",
                      "claimed_at": datetime.now(UTC).isoformat()}},
            sort=[("created_at", 1)],
            return_document=True,
        )
        return CrawlTask(**doc) if doc else None

    async def get(self, task_id: str) -> CrawlTask | None:
        doc = await self._col.find_one({"_id": task_id})
        return CrawlTask(**doc) if doc else None
```

注意：`find_one_and_update` 的 `return_document=True`（pymongo 的 `ReturnDocument.AFTER` 等價；mongomock_motor 支援 bool）。若 mongomock 版本不吃 `return_document=True`，改用 `from pymongo import ReturnDocument` 並傳 `return_document=ReturnDocument.AFTER`。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_crawl_queue.py
git commit -m "feat(be): CrawlTaskRepository enqueue + 原子 claim"
```

---

### Task 3: CrawlTaskRepository — complete + fail

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`（`CrawlTaskRepository` 內）
- Test: `backend/tests/test_crawl_queue.py`（追加）

**Interfaces:**
- Produces:
  - `async complete(task_id: str, raw_json: dict) -> CrawlTask | None`（設 status=done、存 raw_json、completed_at；回更新後 task）
  - `async fail(task_id: str, error: str) -> CrawlTask | None`（設 status=failed、error、completed_at）

- [ ] **Step 1: 寫失敗測試**

追加到 `backend/tests/test_crawl_queue.py`：

```python
@pytest.mark.asyncio
async def test_complete_stores_raw_and_marks_done():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    await repo.claim()
    done = await repo.complete("t1", {"data": [{"jobNo": "1"}]})
    assert done.status == "done"
    assert done.raw_json == {"data": [{"jobNo": "1"}]}
    assert done.completed_at is not None


@pytest.mark.asyncio
async def test_fail_marks_failed_with_error():
    repo = CrawlTaskRepository(AsyncMongoMockClient()["test"])
    await repo.enqueue(_task("t1"))
    await repo.claim()
    failed = await repo.fail("t1", "403 Forbidden")
    assert failed.status == "failed"
    assert failed.error == "403 Forbidden"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -k "complete or fail" -v`
Expected: FAIL（`AttributeError: ... has no attribute 'complete'`）

- [ ] **Step 3: 實作**

在 `CrawlTaskRepository` 內新增：

```python
    async def complete(self, task_id: str, raw_json: dict) -> CrawlTask | None:
        doc = await self._col.find_one_and_update(
            {"_id": task_id},
            {"$set": {"status": "done", "raw_json": raw_json,
                      "completed_at": datetime.now(UTC).isoformat()}},
            return_document=True,
        )
        return CrawlTask(**doc) if doc else None

    async def fail(self, task_id: str, error: str) -> CrawlTask | None:
        doc = await self._col.find_one_and_update(
            {"_id": task_id},
            {"$set": {"status": "failed", "error": error,
                      "completed_at": datetime.now(UTC).isoformat()}},
            return_document=True,
        )
        return CrawlTask(**doc) if doc else None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_crawl_queue.py
git commit -m "feat(be): CrawlTaskRepository complete + fail"
```

---

### Task 4: CrawlTaskRepository — reap（過期 pending + 回收 stale claimed）

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`（`CrawlTaskRepository` 內）
- Test: `backend/tests/test_crawl_queue.py`（追加）

**Interfaces:**
- Produces: `async reap(pending_ttl_sec: int, claimed_ttl_sec: int) -> None`
  - `pending` 且 `created_at` 早於 now-pending_ttl → status=expired
  - `claimed` 且 `claimed_at` 早於 now-claimed_ttl → status=pending（退回重派）、清 claimed_at

- [ ] **Step 1: 寫失敗測試**

追加：

```python
from datetime import UTC, datetime, timedelta


@pytest.mark.asyncio
async def test_reap_expires_old_pending():
    db = AsyncMongoMockClient()["test"]
    repo = CrawlTaskRepository(db)
    await repo.enqueue(_task("old"))
    # 手動把 created_at 改成 25 小時前
    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    await db["crawl_tasks"].update_one({"_id": "old"}, {"$set": {"created_at": old}})
    await repo.reap(pending_ttl_sec=24 * 3600, claimed_ttl_sec=300)
    assert (await repo.get("old")).status == "expired"


@pytest.mark.asyncio
async def test_reap_requeues_stale_claimed():
    db = AsyncMongoMockClient()["test"]
    repo = CrawlTaskRepository(db)
    await repo.enqueue(_task("stuck"))
    await repo.claim()
    stale = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
    await db["crawl_tasks"].update_one({"_id": "stuck"}, {"$set": {"claimed_at": stale}})
    await repo.reap(pending_ttl_sec=24 * 3600, claimed_ttl_sec=300)
    t = await repo.get("stuck")
    assert t.status == "pending"
    assert t.claimed_at is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -k reap -v`
Expected: FAIL（無 `reap`）

- [ ] **Step 3: 實作**

```python
    async def reap(self, pending_ttl_sec: int, claimed_ttl_sec: int) -> None:
        now = datetime.now(UTC)
        pending_cutoff = (now - timedelta(seconds=pending_ttl_sec)).isoformat()
        claimed_cutoff = (now - timedelta(seconds=claimed_ttl_sec)).isoformat()
        await self._col.update_many(
            {"status": "pending", "created_at": {"$lt": pending_cutoff}},
            {"$set": {"status": "expired"}},
        )
        await self._col.update_many(
            {"status": "claimed", "claimed_at": {"$lt": claimed_cutoff}},
            {"$set": {"status": "pending", "claimed_at": None}},
        )
```

在 `repositories.py` 檔頭把 `from datetime import UTC, datetime` 改為 `from datetime import UTC, datetime, timedelta`。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -v`
Expected: PASS（7 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_crawl_queue.py
git commit -m "feat(be): CrawlTaskRepository reap（過期 + 回收）"
```

---

### Task 5: AgentStatusRepository（心跳）

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`（檔末新增）
- Test: `backend/tests/test_crawl_queue.py`（追加）

**Interfaces:**
- Produces: `AgentStatusRepository(db)`，方法：
  - `async touch() -> None`（upsert `_id="agent"`, `last_seen=now`）
  - `async last_seen() -> datetime | None`
  - `async is_online(window_sec: int) -> bool`

- [ ] **Step 1: 寫失敗測試**

追加：

```python
from job_tracker.db.repositories import AgentStatusRepository


@pytest.mark.asyncio
async def test_agent_status_offline_until_touch():
    repo = AgentStatusRepository(AsyncMongoMockClient()["test"])
    assert await repo.last_seen() is None
    assert await repo.is_online(window_sec=30) is False
    await repo.touch()
    assert await repo.last_seen() is not None
    assert await repo.is_online(window_sec=30) is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -k agent_status -v`
Expected: FAIL（無 `AgentStatusRepository`）

- [ ] **Step 3: 實作**

```python
class AgentStatusRepository:
    """記錄本機 agent 最近一次心跳，供前端判斷在線/離線。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["agent_status"]

    async def touch(self) -> None:
        await self._col.update_one(
            {"_id": "agent"},
            {"$set": {"last_seen": datetime.now(UTC).isoformat()}},
            upsert=True,
        )

    async def last_seen(self) -> datetime | None:
        doc = await self._col.find_one({"_id": "agent"})
        if not doc or "last_seen" not in doc:
            return None
        return datetime.fromisoformat(doc["last_seen"])

    async def is_online(self, window_sec: int) -> bool:
        seen = await self.last_seen()
        if seen is None:
            return False
        return (datetime.now(UTC) - seen).total_seconds() <= window_sec
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_crawl_queue.py -v`
Expected: PASS（8 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_crawl_queue.py
git commit -m "feat(be): AgentStatusRepository 心跳"
```

---

### Task 6: config 設定 + verify_agent 認證依賴

**Files:**
- Modify: `backend/src/job_tracker/config.py`
- Modify: `backend/src/job_tracker/api/deps.py`
- Test: `backend/tests/test_agent_api.py`（新增，僅測認證依賴）

**Interfaces:**
- Produces:
  - config 欄位：`agent_secret:str=""`、`agent_offline_after_sec:int=30`、`crawl_pending_ttl_sec:int=86400`、`crawl_claimed_ttl_sec:int=300`
  - deps：`get_crawl_task_repo()->CrawlTaskRepository`、`get_agent_status_repo()->AgentStatusRepository`、`verify_agent(authorization: str = Header(None)) -> None`（密鑰不符或未設 → 401/503）

- [ ] **Step 1: 寫失敗測試**

新增 `backend/tests/test_agent_api.py`：

```python
import httpx
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.config import get_settings
from job_tracker.main import app


@pytest.fixture
def _secret(monkeypatch):
    monkeypatch.setenv("AGENT_SECRET", "s3cr3t")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_claim_rejects_wrong_secret(_secret):
    db = AsyncMongoMockClient()["test"]
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: deps.CrawlTaskRepository(db)
    app.dependency_overrides[deps.get_agent_status_repo] = lambda: deps.AgentStatusRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/claim", headers={"Authorization": "Bearer wrong"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 401
```

（此測試依賴 Task 7 的 `/api/agent/claim` 路由；本任務先讓 `verify_agent`、deps、config 到位，路由在 Task 7 補上後本測試才會綠。若先跑會是 404 → 視為紅，Task 7 完成轉綠。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_agent_api.py -v`
Expected: FAIL（`AttributeError: module 'deps' has no attribute 'get_crawl_task_repo'`）

- [ ] **Step 3: 實作 config**

在 `backend/src/job_tracker/config.py` 的 `Settings` 內（`log_level` 前）新增：

```python
    # 本機爬蟲 agent
    agent_secret: str = ""           # 與 agent 共享的密鑰；空 = 停用 agent 端點
    agent_offline_after_sec: int = 30   # 超過幾秒沒心跳視為離線
    crawl_pending_ttl_sec: int = 86400  # pending 任務過期（24h）
    crawl_claimed_ttl_sec: int = 300    # claimed 逾時回收（5min）
```

- [ ] **Step 4: 實作 deps**

在 `backend/src/job_tracker/api/deps.py`：

import 區加入 `CrawlTaskRepository, AgentStatusRepository`：

```python
from job_tracker.db.repositories import (
    ApplicationRepository,
    AgentStatusRepository,
    CrawlTaskRepository,
    JobRepository,
    MatchRepository,
    QuotaRepository,
    SearchRepository,
    TokenUsageRepository,
)
from fastapi import Header, HTTPException
```

`__all__` 追加 `"get_crawl_task_repo", "get_agent_status_repo", "verify_agent"`，並新增：

```python
def get_crawl_task_repo() -> CrawlTaskRepository:
    return CrawlTaskRepository(get_db())


def get_agent_status_repo() -> AgentStatusRepository:
    return AgentStatusRepository(get_db())


def verify_agent(authorization: str = Header(default="")) -> None:
    """驗證 agent 共享密鑰。未設 secret → 503（agent 停用）；不符 → 401。"""
    secret = get_settings().agent_secret
    if not secret:
        raise HTTPException(status_code=503, detail="agent 端點未啟用")
    if authorization != f"Bearer {secret}":
        raise HTTPException(status_code=401, detail="agent 密鑰錯誤")
```

（`deps.py` 既有 `from fastapi import HTTPException`，改成同時 import `Header`。）

- [ ] **Step 5: 跑測試**

Run: `cd backend && uv run pytest tests/test_agent_api.py -v`
Expected: 仍 FAIL（404，路由未建）——這是預期，Task 7 補路由後轉綠。先確認不是 import 錯誤即可：
Run: `cd backend && uv run python -c "from job_tracker.api import deps; print(deps.get_crawl_task_repo, deps.verify_agent)"`
Expected: 印出兩個函式，無錯。

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/config.py backend/src/job_tracker/api/deps.py backend/tests/test_agent_api.py
git commit -m "feat(be): agent config 設定 + verify_agent 認證依賴"
```

---

## 階段 B — crawler 解析抽取（供雲端解析 agent 回傳的原始 JSON）

### Task 7: 抽出 parse_search_payload + agent router（claim/complete/status）

**Files:**
- Modify: `backend/src/job_tracker/crawler/__init__.py`
- Create: `backend/src/job_tracker/api/routers/agent.py`
- Modify: `backend/src/job_tracker/main.py`（註冊 router）
- Test: `backend/tests/test_crawler.py`（追加 parse_search_payload）、`backend/tests/test_agent_api.py`（補 claim/complete/status）

**Interfaces:**
- Consumes: `CrawlTaskRepository`、`AgentStatusRepository`、`verify_agent`（Task 6）、`_parse_job`/`_is_relevant`（既有）
- Produces:
  - crawler：`parse_search_payload(payload: dict, keyword: str) -> list[tuple[Job, bool]]`，且 `crawl_jobs` 改用它
  - router `agent.py`，prefix `/agent`：
    - `POST /agent/claim` → `{task: CrawlTask|null}`（更新心跳、reap、claim）
    - `POST /agent/complete`（body `{task_id, raw_json?, error?}`）→ 派工處理（本任務先只標 done/failed，實際解析在 Task 9 接上）
    - `GET /agent/status` → `{online: bool, last_seen: str|null, pending: int}`

- [ ] **Step 1: 寫失敗測試（crawler 抽取）**

在 `backend/tests/test_crawler.py` 追加：

```python
from job_tracker.crawler import parse_search_payload


def test_parse_search_payload_returns_jobs_with_relevance():
    out = parse_search_payload(load_payload(), "python")
    assert len(out) == 2
    job, rel = out[0]
    assert job.job_id == "14724003"
    assert rel is True  # descSnippet 有 [[[Python]]]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_crawler.py -k parse_search_payload -v`
Expected: FAIL（無 `parse_search_payload`）

- [ ] **Step 3: 實作 crawler 抽取**

在 `backend/src/job_tracker/crawler/__init__.py` 新增，並讓 `crawl_jobs` 複用：

```python
def parse_search_payload(payload: dict, keyword: str) -> list[tuple[Job, bool]]:
    """把 104 搜尋 API 的原始 JSON 解析成 [(Job, relevant)]。供雲端解析 agent 回傳用。"""
    return [
        (_parse_job(raw), _is_relevant(raw, keyword))
        for raw in payload.get("data", [])
    ]
```

把 `crawl_jobs` 內原本的 list comprehension：

```python
        out = [
            (_parse_job(raw), _is_relevant(raw, keyword))
            for raw in payload.get("data", [])
        ]
```

改成：

```python
        out = parse_search_payload(payload, keyword)
```

- [ ] **Step 4: 跑 crawler 測試**

Run: `cd backend && uv run pytest tests/test_crawler.py -v`
Expected: PASS（16 passed）

- [ ] **Step 5: 寫 agent router**

新增 `backend/src/job_tracker/api/routers/agent.py`：

```python
"""本機爬蟲 agent 端點（機器對機器，共享密鑰認證）。

agent 輪詢 claim 認領任務 → 用住宅 IP 抓 104 → complete 回填原始 JSON。
complete 的派工處理（解析存候選 / 跑 LLM）在 services 層，見 process_completed_task。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from job_tracker.api.deps import (
    get_agent_status_repo, get_crawl_task_repo, verify_agent,
)
from job_tracker.config import get_settings
from job_tracker.db.repositories import AgentStatusRepository, CrawlTaskRepository
from job_tracker.schemas import CrawlTask

router = APIRouter(prefix="/agent", tags=["agent"], dependencies=[Depends(verify_agent)])


class CompleteRequest(BaseModel):
    task_id: str
    raw_json: dict | None = None
    error: str | None = None


@router.post("/claim")
async def claim_task(
    status_repo: AgentStatusRepository = Depends(get_agent_status_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    await status_repo.touch()
    s = get_settings()
    await queue.reap(s.crawl_pending_ttl_sec, s.crawl_claimed_ttl_sec)
    task = await queue.claim()
    return {"task": task.model_dump(mode="json") if task else None}


@router.post("/complete")
async def complete_task(
    req: CompleteRequest,
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    if req.error is not None:
        await queue.fail(req.task_id, req.error)
        return {"ok": True, "status": "failed"}
    await queue.complete(req.task_id, req.raw_json or {})
    # 解析/LLM 派工在 Task 9 接上
    return {"ok": True, "status": "done"}


@router.get("/status")
async def agent_status(
    status_repo: AgentStatusRepository = Depends(get_agent_status_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    s = get_settings()
    online = await status_repo.is_online(s.agent_offline_after_sec)
    seen = await status_repo.last_seen()
    pending = await queue._col.count_documents({"status": {"$in": ["pending", "claimed"]}})
    return {"online": online, "last_seen": seen.isoformat() if seen else None,
            "pending": pending}
```

（`GET /agent/status` 要給前端輪詢，但前端使用者沒有 agent 密鑰 → 見 Task 11：前端改打雲端的公開 `/api/agent-status`。本路由的 status 供 agent/除錯用；前端用另一個無密鑰端點。為避免重複，**改為**：把 `/agent/status` 從這個受保護 router 移除，狀態查詢另開公開端點，見 Task 11。本步驟先不放 status，只放 claim/complete。）

> 實作修正：上面 router **不要**包含 `agent_status`／`GET /status`。只保留 `claim` 與 `complete`。狀態查詢端點在 Task 11 以公開（免密鑰）形式新增。

- [ ] **Step 6: 註冊 router**

在 `backend/src/job_tracker/main.py` 找到既有 `app.include_router(...)` 區塊，比照加入：

```python
from job_tracker.api.routers import agent as agent_router
...
app.include_router(agent_router.router, prefix="/api")
```

（prefix 與其他 router 一致，最終路徑為 `/api/agent/claim`。）

- [ ] **Step 7: 補 agent_api 測試（claim/complete）**

在 `backend/tests/test_agent_api.py` 追加：

```python
def _wire(db):
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: deps.CrawlTaskRepository(db)
    app.dependency_overrides[deps.get_agent_status_repo] = lambda: deps.AgentStatusRepository(db)


@pytest.mark.asyncio
async def test_claim_returns_pending_task_with_secret(_secret):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.schemas import CrawlTask
    await deps.CrawlTaskRepository(db).enqueue(
        CrawlTask(task_id="t1", type="search",
                  payload={"keyword": "ai", "page": 1, "area": None},
                  search_id="s1", user="u@x"))
    _wire(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/claim", headers={"Authorization": "Bearer s3cr3t"})
    finally:
        app.dependency_overrides.clear()
    body = resp.json()
    assert resp.status_code == 200
    assert body["task"]["task_id"] == "t1"


@pytest.mark.asyncio
async def test_complete_marks_done(_secret):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.schemas import CrawlTask
    repo = deps.CrawlTaskRepository(db)
    await repo.enqueue(CrawlTask(task_id="t1", type="search",
                                 payload={"keyword": "ai", "page": 1, "area": None},
                                 search_id="s1", user="u@x"))
    await repo.claim()
    _wire(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/agent/complete",
                                     headers={"Authorization": "Bearer s3cr3t"},
                                     json={"task_id": "t1", "raw_json": {"data": []}})
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["status"] == "done"
    assert (await repo.get("t1")).status == "done"
```

`deps` 需能存取 `CrawlTaskRepository`/`AgentStatusRepository` 名稱——在 `deps.py` 已 import，故 `deps.CrawlTaskRepository` 可用。

- [ ] **Step 8: 跑全部相關測試**

Run: `cd backend && uv run pytest tests/test_agent_api.py tests/test_crawler.py -v`
Expected: PASS（含 Task 6 的 wrong-secret 測試現在轉綠）

- [ ] **Step 9: Commit**

```bash
git add backend/src/job_tracker/crawler/__init__.py backend/src/job_tracker/api/routers/agent.py backend/src/job_tracker/main.py backend/tests/test_crawler.py backend/tests/test_agent_api.py
git commit -m "feat(be): agent claim/complete 端點 + parse_search_payload 抽取"
```

---

## 階段 C — 雲端流程改造（enqueue 取代直連 104）

### Task 8: services/analyze — 結果處理函式（解析候選 / 詳情+LLM）

**Files:**
- Modify: `backend/src/job_tracker/services/analyze.py`
- Test: `backend/tests/test_analyze.py`（追加）

**Interfaces:**
- Consumes: `parse_search_payload`、`parse_job_detail`（crawler）、`job_matching.analyze`、repos
- Produces：
  - `async store_candidates_from_raw(search_id, user, keyword, raw_json, match_repo) -> list[JobMatch]`
  - `async analyze_from_detail_raw(search_id, user, job_id, raw_json, target, job_repo, match_repo, quota, *, llm_client=None) -> None`（解析詳情→存→LLM→set_result→quota.add；失敗 set_failed）

- [ ] **Step 1: 寫失敗測試**

在 `backend/tests/test_analyze.py` 追加（沿用既有 import 風格；若無則補）：

```python
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import JobRepository, MatchRepository, QuotaRepository
from job_tracker.schemas import ResumeTarget
from job_tracker.services import analyze as analyze_svc


@pytest.mark.asyncio
async def test_store_candidates_from_raw_adds_candidates():
    db = AsyncMongoMockClient()["test"]
    match_repo = MatchRepository(db)
    raw = {"data": [
        {"jobNo": "1", "jobName": "Python 工程師", "custName": "A",
         "link": {"job": "https://www.104.com.tw/job/abc"},
         "descSnippet": "[[[Python]]]", "salaryLow": 0, "salaryHigh": 0},
    ]}
    out = await analyze_svc.store_candidates_from_raw("s1", "u@x", "python", raw, match_repo)
    assert len(out) == 1
    assert out[0].job.job_id == "1"
    assert out[0].status == "candidate"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_analyze.py -k store_candidates_from_raw -v`
Expected: FAIL（無 `store_candidates_from_raw`）

- [ ] **Step 3: 實作**

在 `backend/src/job_tracker/services/analyze.py`：import 區把 `from job_tracker.crawler import crawl_jobs, fetch_job_detail` 改為 `from job_tracker.crawler import crawl_jobs, fetch_job_detail, parse_search_payload, parse_job_detail`，並新增：

```python
async def store_candidates_from_raw(
    search_id: str, user: str, keyword: str, raw_json: dict,
    match_repo: MatchRepository,
) -> list[JobMatch]:
    """把 agent 回傳的搜尋原始 JSON 解析成候選並存。"""
    pairs = parse_search_payload(raw_json, keyword)
    for job, relevant in pairs:
        await match_repo.add_candidate(search_id, user, job, relevant)
    logger.info("store_candidates s=%s -> %d", search_id, len(pairs))
    return [await match_repo.get_match(search_id, j.job_id) for j, _ in pairs]


async def analyze_from_detail_raw(
    search_id: str, user: str, job_id: str, raw_json: dict,
    target: ResumeTarget, job_repo: JobRepository, match_repo: MatchRepository,
    quota: QuotaRepository, *, llm_client=None,
) -> None:
    """把 agent 回傳的詳情原始 JSON 解析→存→LLM 分析→寫結果。"""
    try:
        cand = await match_repo.get_match(search_id, job_id)
        if cand is None:
            return
        job = cand.job
        detail = parse_job_detail(raw_json)
        if detail.salary:
            job.salary = detail.salary
        await job_repo.upsert_job(job)
        await job_repo.set_detail(job_id, detail)
        analysis = await job_matching.analyze(target, job, detail, client=llm_client)
        await match_repo.set_result(search_id, job_id, analysis)
        await quota.add(user, 1)
    except Exception:
        logger.warning("分析失敗 job=%s", job_id, exc_info=True)
        await match_repo.set_failed(search_id, job_id)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_analyze.py -k store_candidates_from_raw -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/services/analyze.py backend/tests/test_analyze.py
git commit -m "feat(be): 結果處理函式 store_candidates_from_raw / analyze_from_detail_raw"
```

---

### Task 9: complete 端點派工 + SearchRun.crawl_status

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py`（SearchRun 加 `crawl_status`）
- Modify: `backend/src/job_tracker/api/routers/agent.py`（complete 派工）
- Modify: `backend/src/job_tracker/db/repositories.py`（SearchRepository 加 `set_crawl_status`）
- Test: `backend/tests/test_agent_api.py`（追加：complete 觸發解析）

**Interfaces:**
- Produces:
  - `SearchRun.crawl_status: str = "done"`（new search 建立時設 "queued"）
  - `SearchRepository.set_crawl_status(search_id, status) -> None`
  - complete 端點：search 任務 → `store_candidates_from_raw` + `advance_page` + `set_crawl_status("done")`；detail 任務 → 用 runner 背景跑 `analyze_from_detail_raw`

- [ ] **Step 1: 寫失敗測試**

在 `backend/tests/test_agent_api.py` 追加：

```python
@pytest.mark.asyncio
async def test_complete_search_task_stores_candidates(_secret):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.schemas import CrawlTask
    repo = deps.CrawlTaskRepository(db)
    await repo.enqueue(CrawlTask(task_id="t1", type="search",
                                 payload={"keyword": "python", "page": 1, "area": None},
                                 search_id="s1", user="u@x"))
    await repo.claim()
    _wire(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: deps.MatchRepository(db)
    app.dependency_overrides[deps.get_job_repo] = lambda: deps.JobRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: deps.SearchRepository(db)
    raw = {"data": [{"jobNo": "1", "jobName": "Python", "custName": "A",
                     "link": {"job": "https://www.104.com.tw/job/abc"},
                     "descSnippet": "[[[Python]]]", "salaryLow": 0, "salaryHigh": 0}]}
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/agent/complete",
                              headers={"Authorization": "Bearer s3cr3t"},
                              json={"task_id": "t1", "raw_json": raw})
    finally:
        app.dependency_overrides.clear()
    cands = await deps.MatchRepository(db).list_by_search("s1")
    assert [c.job.job_id for c in cands] == ["1"]
```

`deps` 需可存取 `MatchRepository/JobRepository/SearchRepository`——已在 deps.py import，故 `deps.MatchRepository` 可用。

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_agent_api.py -k complete_search_task -v`
Expected: FAIL（complete 尚未解析存候選）

- [ ] **Step 3: schema 加 crawl_status**

在 `SearchRun` 加欄位（`count` 後）：

```python
    crawl_status: str = "done"  # queued|crawling|done|expired|failed（搜尋頁爬取狀態）
```

`SearchRepository.create` 建立時設為 queued：把 `SearchRun(...)` 呼叫補上 `crawl_status="queued"`。

- [ ] **Step 4: SearchRepository.set_crawl_status**

在 `SearchRepository` 內新增：

```python
    async def set_crawl_status(self, search_id: str, status: str) -> None:
        await self._col.update_one({"_id": search_id},
                                   {"$set": {"crawl_status": status}})
```

- [ ] **Step 5: complete 端點派工**

把 `agent.py` 的 `complete_task` 改為依任務型別派工。新增依賴 import：

```python
from job_tracker.api.deps import (
    get_agent_status_repo, get_analysis_runner, get_crawl_task_repo,
    get_job_repo, get_match_repo, get_quota_repo, get_search_repo, verify_agent,
)
from job_tracker.db.repositories import (
    AgentStatusRepository, CrawlTaskRepository, JobRepository,
    MatchRepository, QuotaRepository, SearchRepository,
)
from job_tracker.services import analyze as analyze_svc
from job_tracker.services.analyze import AnalysisRunner
```

改寫 complete：

```python
@router.post("/complete")
async def complete_task(
    req: CompleteRequest,
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    job_repo: JobRepository = Depends(get_job_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
    runner: AnalysisRunner = Depends(get_analysis_runner),
) -> dict:
    if req.error is not None:
        task = await queue.fail(req.task_id, req.error)
        if task and task.type == "search":
            await search_repo.set_crawl_status(task.search_id, "failed")
        elif task and task.job_id:
            await match_repo.set_failed(task.search_id, task.job_id)
        return {"ok": True, "status": "failed"}

    task = await queue.complete(req.task_id, req.raw_json or {})
    if task is None:
        return {"ok": False}
    run = await search_repo.get(task.search_id)
    if task.type == "search":
        cands = await analyze_svc.store_candidates_from_raw(
            task.search_id, task.user, task.payload["keyword"], task.raw_json, match_repo)
        page = task.payload.get("page", 1)
        await search_repo.advance_page(task.search_id, next_page=page + 1, count_delta=len(cands))
        await search_repo.set_crawl_status(task.search_id, "done")
    elif task.type == "detail" and run is not None:
        runner.submit([analyze_svc.analyze_from_detail_raw(
            task.search_id, task.user, task.job_id, task.raw_json,
            run.target, job_repo, match_repo, quota)])
    return {"ok": True, "status": "done"}
```

- [ ] **Step 6: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_agent_api.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/src/job_tracker/api/routers/agent.py backend/src/job_tracker/db/repositories.py backend/tests/test_agent_api.py
git commit -m "feat(be): complete 端點依型別派工（候選/詳情+LLM）+ SearchRun.crawl_status"
```

---

### Task 10: jobs router 改 enqueue（create_search / crawl_next / analyze）

**Files:**
- Modify: `backend/src/job_tracker/api/routers/jobs.py`
- Test: `backend/tests/test_jobs_api.py`（改寫既有測試以符合非同步流程）

**Interfaces:**
- Consumes: `CrawlTaskRepository`、`get_crawl_task_repo`、`store/enqueue`
- Produces（行為改變）：
  - `POST /jobs/searches` → 建 SearchRun（crawl_status=queued）+ enqueue `search` 任務 → 回 `{search_id, status: "queued"}`（不再同步回 candidates）
  - `POST /jobs/searches/{id}/crawl-next` → enqueue 下一頁 `search` 任務 → 回 `{status: "queued"}`
  - `POST /jobs/searches/{id}/analyze` → 額度檢查 + `set_pending` + 每筆 enqueue `detail` 任務（payload `{code}`，job_id 綁定）→ 回 `{queued: n}`

- [ ] **Step 1: 寫失敗測試（改寫）**

把 `backend/tests/test_jobs_api.py` 的 `_wire` 與測試改為 enqueue 模型。新增 helper：直接用 `CrawlTaskRepository` 斷言任務入列。改寫 `test_search_returns_candidates` 為：

```python
@pytest.mark.asyncio
async def test_search_enqueues_search_task(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    from job_tracker.db.repositories import CrawlTaskRepository
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/jobs/searches", json=_PAYLOAD)
            body = resp.json()
    finally:
        app.dependency_overrides.clear()
    assert body["search_id"] and body["status"] == "queued"
    task = await CrawlTaskRepository(db).claim()
    assert task.type == "search" and task.payload["keyword"] == "python"
```

並把 `test_analyze_selected_runs_and_counts_quota` 改為斷言 detail 任務入列（不再 monkeypatch analyze_one）：

```python
@pytest.mark.asyncio
async def test_analyze_enqueues_detail_tasks(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.db.repositories import CrawlTaskRepository
    from job_tracker.schemas import Job
    match_repo = MatchRepository(db)
    search_repo = SearchRepository(db)
    run = await search_repo.create("dev@local", "python",
                                   {"target_title": "後端", "expected_salary": 70000,
                                    "resume_text": "Python"})
    await match_repo.add_candidate(run.search_id, "dev@local",
                                   Job(job_id="1", code="abc", title="t", company="c",
                                       url="https://x/abc"), True)
    app.dependency_overrides[deps.get_match_repo] = lambda: match_repo
    app.dependency_overrides[deps.get_search_repo] = lambda: search_repo
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(f"/api/jobs/searches/{run.search_id}/analyze",
                                     json={"job_ids": ["1"]})
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["queued"] == 1
    task = await CrawlTaskRepository(db).claim()
    assert task.type == "detail" and task.job_id == "1" and task.payload["code"] == "abc"
    assert (await match_repo.get_match(run.search_id, "1")).status == "pending"
```

保留 `test_analyze_over_quota_is_429`、`test_analyze_skips_already_done`、`test_analyze_allows_retry_failed`，但移除其中對 `_runner_instance._task` 的等待與 `fake_analyze_one`（改為斷言任務入列 / 狀態），並為它們補上 `get_crawl_task_repo` override。刪除舊的 `_wire`/`SyncRunner`/`fake_crawl`/`fake_analyze_one`。

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_jobs_api.py -v`
Expected: FAIL（目前 create_search 仍同步回 candidates）

- [ ] **Step 3: 改寫 jobs router**

`backend/src/job_tracker/api/routers/jobs.py`：

import 區加入：

```python
from uuid import uuid4
from job_tracker.api.deps import get_crawl_task_repo
from job_tracker.db.repositories import CrawlTaskRepository
from job_tracker.schemas import CrawlTask
```

改寫三個端點：

```python
@router.post("/searches")
async def create_search(
    req: CreateSearchRequest,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    run = await search_repo.create(user, req.keyword, req.target, area=req.area)
    await queue.enqueue(CrawlTask(
        task_id=uuid4().hex, type="search",
        payload={"keyword": req.keyword, "page": 1, "area": req.area},
        search_id=run.search_id, user=user))
    return {"search_id": run.search_id, "status": "queued"}


@router.post("/searches/{search_id}/crawl-next")
async def crawl_next(
    search_id: str,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    run = await _ensure_owned(search_id, user, search_repo)
    await search_repo.set_crawl_status(search_id, "queued")
    await queue.enqueue(CrawlTask(
        task_id=uuid4().hex, type="search",
        payload={"keyword": run.keyword, "page": run.next_page, "area": run.area},
        search_id=search_id, user=user))
    return {"status": "queued"}


@router.post("/searches/{search_id}/analyze")
async def analyze_selected(
    search_id: str,
    req: AnalyzeRequest,
    user: str = Depends(current_user),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    await _ensure_owned(search_id, user, search_repo)
    valid = []
    for jid in req.job_ids:
        m = await match_repo.get_match(search_id, jid)
        if m is not None and m.status in ("candidate", "failed"):
            valid.append((jid, m.job.code))
    if not valid:
        raise HTTPException(status_code=400, detail="沒有可分析的候選職缺")
    limit = get_settings().daily_call_limit
    if await quota.used_today(user) + len(valid) > limit:
        raise HTTPException(status_code=429, detail=f"今日額度不足（每日 {limit} 次）")
    await match_repo.set_pending(search_id, [jid for jid, _ in valid])
    for jid, code in valid:
        await queue.enqueue(CrawlTask(
            task_id=uuid4().hex, type="detail", payload={"code": code},
            search_id=search_id, user=user, job_id=jid))
    return {"queued": len(valid)}
```

移除已不再使用的 import（`crawl_candidates`、`analyze_one`、`AnalysisRunner`、`get_analysis_runner`、`get_job_repo` 若未用）。`crawl_candidates`/`analyze_one`/`AsyncioRunner` 仍保留在 `services/analyze.py`（未來本機直連模式可能用，且 `get_analysis_runner` 仍被 agent complete 用）。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_jobs_api.py -v`
Expected: PASS

- [ ] **Step 5: 跑全後端測試（回歸）**

Run: `cd backend && uv run pytest -q`
Expected: 全綠（既有 + 新增）。若 `crawl_candidates`/`analyze_one` 的舊測試（test_analyze.py 內）因簽名仍在而通過則保留。

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/api/routers/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat(be): jobs 端點改 enqueue 任務（搜尋/詳情非同步）"
```

---

## 階段 D — 公開狀態端點 + 單筆搜尋查詢

### Task 11: 前端用的公開 agent 狀態 + 單筆 search 查詢端點

**Files:**
- Modify: `backend/src/job_tracker/api/routers/jobs.py`（加 `GET /jobs/searches/{id}` 與 `GET /jobs/agent-status`）
- Test: `backend/tests/test_jobs_api.py`（追加）

**Interfaces:**
- Produces（需登入，前端用）：
  - `GET /api/jobs/searches/{id}` → `SearchRun`（含 crawl_status）
  - `GET /api/jobs/agent-status` → `{online: bool, pending: int}`

- [ ] **Step 1: 寫失敗測試**

追加：

```python
@pytest.mark.asyncio
async def test_get_single_search_returns_crawl_status(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    search_repo = SearchRepository(db)
    run = await search_repo.create("dev@local", "python",
                                   {"target_title": "後端", "expected_salary": None,
                                    "resume_text": "x"})
    app.dependency_overrides[deps.get_search_repo] = lambda: search_repo
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(f"/api/jobs/searches/{run.search_id}")
    finally:
        app.dependency_overrides.clear()
    assert resp.json()["crawl_status"] == "queued"


@pytest.mark.asyncio
async def test_agent_status_endpoint(monkeypatch):
    db = AsyncMongoMockClient()["test"]
    from job_tracker.db.repositories import AgentStatusRepository, CrawlTaskRepository
    app.dependency_overrides[deps.get_agent_status_repo] = lambda: AgentStatusRepository(db)
    app.dependency_overrides[deps.get_crawl_task_repo] = lambda: CrawlTaskRepository(db)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/jobs/agent-status")
    finally:
        app.dependency_overrides.clear()
    body = resp.json()
    assert body["online"] is False and body["pending"] == 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_jobs_api.py -k "single_search or agent_status_endpoint" -v`
Expected: FAIL（404）

- [ ] **Step 3: 實作端點**

在 `jobs.py` import 加 `get_agent_status_repo`、`AgentStatusRepository`，新增：

```python
@router.get("/searches/{search_id}")
async def get_search(
    search_id: str,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> SearchRun:
    return await _ensure_owned(search_id, user, search_repo)


@router.get("/agent-status")
async def agent_status(
    user: str = Depends(current_user),
    status_repo: AgentStatusRepository = Depends(get_agent_status_repo),
    queue: CrawlTaskRepository = Depends(get_crawl_task_repo),
) -> dict:
    s = get_settings()
    online = await status_repo.is_online(s.agent_offline_after_sec)
    pending = await queue._col.count_documents({"status": {"$in": ["pending", "claimed"]}})
    return {"online": online, "pending": pending}
```

注意：`GET /searches/{id}` 須放在 `GET /searches`（列表）之後、且不與 `/searches/{id}/matches` 衝突——FastAPI 依宣告順序，確保 `/agent-status` 與 `/searches/{search_id}` 不會誤吞既有路徑（`agent-status` 非 `searches` 子路徑，安全）。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_jobs_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/api/routers/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat(be): 公開 agent 狀態 + 單筆 search 查詢端點"
```

---

## 階段 E — 本機 agent

### Task 12: 本機 agent script

**Files:**
- Create: `agent/agent.py`
- Create: `agent/pyproject.toml`
- Create: `agent/.env.example`
- Create: `agent/README.md`
- Test: `agent/test_agent.py`

**Interfaces:**
- Consumes: 雲端 `/api/agent/claim`、`/api/agent/complete`
- Produces（agent 內部函式，供測試）：
  - `fetch_104(task: dict, client) -> dict`（依 task.type 組 104 URL，帶完整 header + 暖身，回原始 JSON）
  - `run_once(client, cloud_base, secret) -> str`（claim 一次；有任務則抓+complete，回 "done"/"failed"/"idle"）

- [ ] **Step 1: 建 agent 專案骨架**

`agent/pyproject.toml`：

```toml
[project]
name = "career-agent-crawler"
version = "0.1.0"
description = "本機爬蟲 agent：用住宅 IP 代打 104，回填雲端。"
requires-python = ">=3.11"
dependencies = ["httpx>=0.27", "python-dotenv>=1.0"]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23"]
```

`agent/.env.example`：

```
# 雲端後端網址（不含結尾斜線）
CLOUD_BASE_URL=https://career-agent.zeabur.app
# 與雲端 AGENT_SECRET 相同的共享密鑰
AGENT_SECRET=
# 輪詢間隔（秒）
POLL_INTERVAL=3
# detail 任務之間的節流（秒），避免被 104 鎖
MIN_DELAY=2
MAX_DELAY=5
```

`agent/README.md`：

```markdown
# 本機爬蟲 agent

用家用住宅 IP 代打 104（雲端機房 IP 被 104 封）。輪詢雲端任務隊列 → 抓 104 → 回填原始 JSON。

## 跑法

1. `cp .env.example .env`，填 `CLOUD_BASE_URL` 與 `AGENT_SECRET`（與雲端設定相同）。
2. `uv sync`
3. `uv run python agent.py`

需要爬職缺時開著即可；關掉則任務在雲端排隊，下次開機自動跑完。
```

- [ ] **Step 2: 寫失敗測試**

`agent/test_agent.py`：

```python
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
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd agent && uv run pytest -v`
Expected: FAIL（無 `agent` 模組）

- [ ] **Step 4: 實作 agent**

`agent/agent.py`：

```python
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
```

`agent/pyproject.toml` 補 pytest asyncio 設定（檔末）：

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd agent && uv run pytest -v`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add agent/
git commit -m "feat: 本機爬蟲 agent（住宅 IP 代打 104）"
```

---

## 階段 F — 前端

### Task 13: 前端 API client + 型別（agent 狀態 / 非同步搜尋）

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/types/index.ts`
- Test: 無（型別/薄封裝，行為在 Task 14 的頁面層驗證）

**Interfaces:**
- Produces（client）：
  - `api.createSearch` 回 `{search_id: string; status: string}`（移除 candidates）
  - `api.crawlNext(id)` 回 `{status: string}`
  - `api.getSearch(id)` → `SearchRun`（含 `crawl_status`）
  - `api.agentStatus()` → `{online: boolean; pending: number}`
- Produces（types）：`SearchRun` 介面加 `crawl_status: string`

- [ ] **Step 1: 看現有 client 形狀**

Run: `cd frontend && sed -n '1,80p' src/api/client.ts`
觀察既有 `createSearch`/`crawlNext`/`listSearches` 寫法與 `req`/`get` helper 命名，照同風格加。

- [ ] **Step 2: 改 client**

在 `frontend/src/api/client.ts` 的 `api` 物件內：
- `createSearch`：回傳型別改 `{ search_id: string; status: string }`。
- `crawlNext`：回傳型別改 `{ status: string }`。
- 新增 `getSearch: (id: string) => req<SearchRun>(\`/jobs/searches/${id}\`)`（GET）。
- 新增 `agentStatus: () => req<{ online: boolean; pending: number }>("/jobs/agent-status")`（GET）。

（依該檔既有的 fetch 封裝函式名稱調整；若既有用 `get<T>(path)` 就用 `get`。）

- [ ] **Step 3: 改 types**

在 `frontend/src/types/index.ts` 的 `SearchRun` 介面加：

```typescript
  crawl_status: string; // queued|crawling|done|expired|failed
```

- [ ] **Step 4: build 驗證**

Run: `cd frontend && npm run build`
Expected: build 成功（型別無誤）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/types/index.ts
git commit -m "feat(fe): API client 加 agent 狀態 / 單筆 search 查詢"
```

---

### Task 14: JobList 非同步搜尋 UX + 爬蟲狀態指示燈

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`
- Test: 無自動化（前端互動）；以 build + 手動驗證

**Interfaces:**
- Consumes: `api.createSearch`（回 queued）、`api.getSearch`、`api.agentStatus`
- Produces（UI 行為）：
  - 加 `agentStatus` 查詢（`refetchInterval` 15s），控制列顯示 🟢 在線 / ⚪ 離線（pending 數）
  - `createMut.onSuccess` 不再有 candidates；改為設 `selectedId` 並開始輪詢
  - candidates 為空且該 search `crawl_status in (queued, crawling)` 時，候選區顯示「排隊中·等爬蟲上線 / 爬取中…」；`crawl_status==="expired"` 顯示「已過期，請重新搜尋」
  - `matchesQ` 輪詢條件擴充：除既有「有 pending」外，「該 search crawl_status 為 queued/crawling」時也持續輪詢

- [ ] **Step 1: 加 agentStatus 查詢與指示燈**

在 `JobList` 元件內，靠近其他 `useQuery` 處新增：

```tsx
const agentQ = useQuery({
  queryKey: ["agent-status"],
  queryFn: api.agentStatus,
  refetchInterval: 15000,
});
```

在控制列（「爬取候選」按鈕附近）加指示燈：

```tsx
<Text fz="xs" c={agentQ.data?.online ? "teal" : "dimmed"}>
  {agentQ.data?.online ? "🟢 爬蟲在線" : "⚪ 爬蟲離線"}
  {agentQ.data && agentQ.data.pending > 0 ? ` · 排隊 ${agentQ.data.pending}` : ""}
</Text>
```

- [ ] **Step 2: 改 createMut.onSuccess**

把原本依賴 `data.candidates` 的邏輯改為：

```tsx
const createMut = useMutation({
  mutationFn: api.createSearch,
  onSuccess: (data) => {
    setSelectedId(data.search_id);
    setPicked(new Set());
    qc.invalidateQueries({ queryKey: ["searches"] });
    qc.invalidateQueries({ queryKey: ["search-matches", data.search_id] });
  },
});
```

`crawlMut` 的 `onSuccess` 同樣移除對 `data.candidates` 的依賴，只 `invalidateQueries(["search-matches", selectedId])`。

- [ ] **Step 3: 加單筆 search 輪詢（crawl_status）**

新增：

```tsx
const searchQ = useQuery({
  queryKey: ["search", selectedId],
  queryFn: () => api.getSearch(selectedId!),
  enabled: !!selectedId,
  refetchInterval: (q) =>
    ["queued", "crawling"].includes(q.state.data?.crawl_status ?? "") ? 2500 : false,
});
const crawlStatus = searchQ.data?.crawl_status;
```

把 `matchesQ` 的 `refetchInterval` 改為：

```tsx
refetchInterval: (q) => {
  const hasPending = (q.state.data ?? []).some((m) => m.status === "pending");
  const crawling = ["queued", "crawling"].includes(crawlStatus ?? "");
  return hasPending || crawling ? 2500 : false;
},
```

- [ ] **Step 4: 候選區空狀態文案**

在候選清單為空、結果也為空時，依 `crawlStatus` 顯示對應狀態。於「結果」面板的空狀態分支加入判斷：

```tsx
) : crawlStatus === "queued" || crawlStatus === "crawling" ? (
  <div className="jt-empty">
    {agentQ.data?.online ? "爬取中…請稍候" : "排隊中 · 等爬蟲上線"}
  </div>
) : crawlStatus === "expired" ? (
  <div className="jt-empty">已過期 // 請重新搜尋</div>
) : (
  <div className="jt-empty">
    尚無結果 // 輸入關鍵字後執行「爬取候選」，勾選後「分析選中」
  </div>
)}
```

（插在既有 `results.length ? (...) : (...)` 的最後 else 之前，形成多分支。）

- [ ] **Step 5: build 驗證**

Run: `cd frontend && npm run build`
Expected: build 成功。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(fe): 職缺頁非同步搜尋 UX + 爬蟲在線/離線指示燈"
```

---

## 階段 G — 文件與部署設定

### Task 15: DEPLOY.md + .env.example 補 agent

**Files:**
- Modify: `docs/DEPLOY.md`
- Modify: `backend/.env.example`

- [ ] **Step 1: backend .env.example 加 AGENT_SECRET**

在 `backend/.env.example` 適當處新增：

```
# 本機爬蟲 agent 共享密鑰（與 agent/.env 的 AGENT_SECRET 相同；空 = 停用 agent 端點）
AGENT_SECRET=
```

- [ ] **Step 2: DEPLOY.md 加 agent 章節**

在 `docs/DEPLOY.md` 環境變數表加一列 `AGENT_SECRET`，並新增一節「本機爬蟲 agent」說明：為何需要（104 封機房 IP）、Zeabur 設 `AGENT_SECRET`、本機 `agent/` 設相同密鑰 + `CLOUD_BASE_URL` 後 `uv run python agent.py`、需要爬職缺時開著。

- [ ] **Step 3: Commit**

```bash
git add docs/DEPLOY.md backend/.env.example
git commit -m "docs: DEPLOY.md + .env.example 補本機爬蟲 agent 設定"
```

---

### Task 16: 全回歸 + PROGRESS 更新

**Files:**
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: 後端全測試**

Run: `cd backend && uv run pytest -q`
Expected: 全綠。

- [ ] **Step 2: 前端 build**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 3: agent 測試**

Run: `cd agent && uv run pytest -q`
Expected: 全綠。

- [ ] **Step 4: 更新 PROGRESS.md**

在 `docs/PROGRESS.md` 加一節記錄本機爬蟲 agent 子系統（對應本 spec/plan）：104 封機房 IP、改任務隊列 + 住宅 IP agent、離線排隊、心跳指示燈。

- [ ] **Step 5: Commit**

```bash
git add docs/PROGRESS.md
git commit -m "docs: PROGRESS 記錄本機爬蟲 agent 子系統"
```

---

## Self-Review（已執行）

**Spec coverage：**
- IP 封鎖背景 / agent 笨取數器 → Task 12（agent 只回原始 JSON）✅
- MongoDB 任務隊列 → Task 2–4 ✅
- 兩種任務型別 search/detail → Task 1 schema、Task 10 enqueue、Task 9 派工 ✅
- agent 端點 claim/complete + 認證 → Task 6–7、Task 9 ✅
- 心跳/離線偵測 → Task 5、Task 11、Task 14 ✅
- 過期/回收 → Task 4、Task 7（claim 時 reap）✅
- 流程改非同步 + 前端排隊 UX → Task 10、Task 13–14 ✅
- 錯誤處理（failed 回填 + 重試）→ Task 9（complete error 分支）、既有 failed 重試 UI 沿用 ✅
- 測試策略 → 每個後端 Task 皆 TDD，agent Task 12 用 MockTransport ✅

**Placeholder scan：** 無 TBD/TODO；每個 code 步驟含實際程式碼。

**Type consistency：** `CrawlTask` 欄位於 Task 1 定義，Task 2–10 一致使用；`crawl_status` 字串集合（queued/crawling/done/expired/failed）於 schema、router、前端一致；`parse_search_payload(payload, keyword)` 簽名於 Task 7 定義、Task 8 使用一致。

**注意事項（實作時）：**
- `find_one_and_update` 的 `return_document` 參數若 mongomock_motor 版本不支援 bool，改用 `pymongo.ReturnDocument.AFTER`（Task 2 已註明）。
- Task 10 改寫 `test_jobs_api.py` 時，須一併移除舊的 `_wire`/`SyncRunner`/`fake_*`，避免殘留 import 報錯。
- `crawl_candidates` / `analyze_one` / `AsyncioRunner` 保留在 `services/analyze.py`（agent complete 仍用 runner），不刪除。
