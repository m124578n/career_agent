# 分析歷史紀錄 ＋ 求職追蹤清單 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「每次爬取並分析」保留成可回顧的搜尋歷史（search runs），並讓使用者把職缺加入五欄看板的求職追蹤清單。

**Architecture:** 後端新增 `searches` 與 `applications` 兩個 collection；`matches` 改以 `search_id|job_id` 為主鍵綁定到 search。每次新搜尋建立一筆 `SearchRun`，「分析下一批」沿用該 run 的 keyword/target/next_offset 續抓。求職信 modal 生成完成後提供「加入追蹤」鈕，把 job 與求職信快照寫入 `applications`。

**Tech Stack:** FastAPI + motor（mongomock-motor 測試）、Pydantic v2、Python 3.14/uv、React + Vite + TS + Mantine + React Query。

## Global Constraints

- TDD 嚴格 Red-Green-Refactor：先寫測試、跑到失敗、再寫最小實作、跑到通過、commit。
- 後端測試以 `uv run pytest` 執行（cwd = `backend/`）。
- 所有 API 端點需登入（`current_user` 依賴）；測試環境 `GOOGLE_CLIENT_ID=""` 由 `backend/tests/conftest.py` 強制，user 預設 `dev@local`。
- 分析（建立 search／下一批）與生成求職信以實際筆數計入 `daily_usage`；加入追蹤／改狀態不計額度、不呼叫 LLM。
- 單人 dev 階段：舊 `matches` 結構直接清掉重來，不寫遷移腳本。
- 每個後端公開方法的命名與簽名以本計畫 Interfaces 區塊為準，跨 task 必須一致。
- Commit 訊息結尾加：`Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`

---

## File Structure

**後端**
- `backend/src/job_tracker/schemas/__init__.py` — 新增 `SearchRun`、`ApplicationEvent`；改造 `Application`、`ApplicationStatus`
- `backend/src/job_tracker/db/repositories.py` — 新增 `SearchRepository`、`ApplicationRepository`；改造 `MatchRepository`
- `backend/src/job_tracker/services/analyze.py` — `analyze_jobs` 改以 `search_id` 寫入
- `backend/src/job_tracker/api/deps.py` — 新增 `get_search_repo`、`get_application_repo`
- `backend/src/job_tracker/api/routers/jobs.py` — `/analyze`、`/matches` 改為 `/searches` 系列端點
- `backend/src/job_tracker/api/routers/applications.py` — 追蹤 CRUD；cover-letter 移到 jobs/searches
- 測試：`backend/tests/test_search_repository.py`、`test_job_repository.py`（改）、`test_application_repository.py`、`test_jobs_api.py`（改）、`test_applications_api.py`（改）

**前端**
- `frontend/src/types/index.ts` — 新增 `SearchRun`、`Application`、`ApplicationStatus`、`ApplicationEvent`
- `frontend/src/api/client.ts` — searches／applications 呼叫；coverLetter 改路徑
- `frontend/src/pages/JobList.tsx` — 歷史 chips、改打新端點、MatchCard 加入追蹤鈕
- `frontend/src/pages/Applications.tsx` — 新增看板頁
- `frontend/src/App.tsx` — 路由與導覽入口

---

## Task 1: Schema 模型（SearchRun／Application 改造）

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py`
- Test: `backend/tests/test_schemas.py`（新建）

**Interfaces:**
- Produces:
  - `SearchRun(search_id:str, user:str, keyword:str, target:ResumeTarget, created_at:datetime, next_offset:int=0, count:int=0)`
  - `ApplicationStatus` Enum：`TO_APPLY="to_apply"`, `APPLIED="applied"`, `INTERVIEWING="interviewing"`, `OFFER="offer"`, `CLOSED="closed"`
  - `ApplicationEvent(ts:datetime, type:str, note:str="")`
  - `Application(user:str, job_id:str, job:Job, source_search_id:str, cover_letter:str|None=None, status:ApplicationStatus=TO_APPLY, created_at:datetime, updated_at:datetime, events:list[ApplicationEvent]=[])`

- [ ] **Step 1: 先確認舊 Application 的引用**

Run: `cd backend && uv run python -c "import job_tracker.schemas as s; print([n for n in dir(s) if 'Appl' in n])"`
另用 grep 確認舊 `ApplicationStatus.PENDING/EXTERNAL_REQUIRED/SKIPPED` 是否被別處引用：`grep -rn "ApplicationStatus\." backend/src`。預期：僅 schema 自身定義，無其他引用（M6 僅在 router 用字串）。若有引用，於本 task 一併更新。

- [ ] **Step 2: 寫失敗測試**

```python
# backend/tests/test_schemas.py
from job_tracker.schemas import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    Job,
    ResumeTarget,
    SearchRun,
)


def _job() -> Job:
    return Job(job_id="1", code="abc", title="工程師", company="某公司",
               url="https://www.104.com.tw/job/abc")


def test_search_run_defaults():
    run = SearchRun(search_id="s1", user="u1", keyword="python",
                    target=ResumeTarget(target_title="後端", resume_text="x"))
    assert run.next_offset == 0
    assert run.count == 0
    assert run.created_at is not None


def test_application_defaults_to_to_apply():
    app = Application(user="u1", job_id="1", job=_job(), source_search_id="s1")
    assert app.status == ApplicationStatus.TO_APPLY
    assert app.events == []
    assert app.cover_letter is None


def test_application_status_values():
    assert [s.value for s in ApplicationStatus] == [
        "to_apply", "applied", "interviewing", "offer", "closed"
    ]


def test_application_event_shape():
    ev = ApplicationEvent(type="status", note="→ applied")
    assert ev.type == "status"
    assert ev.note == "→ applied"
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'SearchRun'`

- [ ] **Step 4: 實作 schema**

在 `schemas/__init__.py`：新增 `SearchRun`；把 `ApplicationStatus` 改成五值；新增 `ApplicationEvent`；改寫 `Application`。

```python
class SearchRun(BaseModel):
    """一次「爬取並分析」的搜尋紀錄（歷史）。"""

    search_id: str
    user: str
    keyword: str
    target: ResumeTarget
    created_at: datetime = Field(default_factory=_utcnow)
    next_offset: int = 0  # 下一批的 job 列表起點
    count: int = 0         # 累積成功分析筆數


class ApplicationStatus(str, Enum):
    TO_APPLY = "to_apply"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    CLOSED = "closed"


class ApplicationEvent(BaseModel):
    """追蹤時間軸上的一個事件（本期只記狀態變更）。"""

    ts: datetime = Field(default_factory=_utcnow)
    type: str
    note: str = ""


class Application(BaseModel):
    """求職追蹤清單的一筆（以 user|job_id 去重）。"""

    user: str
    job_id: str
    job: Job                       # 加入當下的職缺快照
    source_search_id: str          # 從哪筆 search 加入
    cover_letter: str | None = None  # 加入當下的求職信快照
    status: ApplicationStatus = ApplicationStatus.TO_APPLY
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    events: list[ApplicationEvent] = Field(default_factory=list)
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_schemas.py -v`
Expected: PASS（4 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/tests/test_schemas.py
git commit -m "feat(schema): 新增 SearchRun、改造 Application 為五階段追蹤模型"
```

---

## Task 2: SearchRepository

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`
- Test: `backend/tests/test_search_repository.py`（新建）

**Interfaces:**
- Consumes: `SearchRun`, `ResumeTarget`（Task 1）
- Produces `SearchRepository`：
  - `create(user:str, keyword:str, target:ResumeTarget) -> SearchRun`
  - `get(search_id:str) -> SearchRun | None`
  - `list(user:str) -> list[SearchRun]`（created_at desc）
  - `advance(search_id:str, next_offset:int, count_delta:int) -> None`
  - `delete(search_id:str) -> None`（連帶刪該 search 的 matches）

- [ ] **Step 1: 寫失敗測試**

```python
# backend/tests/test_search_repository.py
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import SearchRepository
from job_tracker.schemas import ResumeTarget


@pytest.fixture
def db():
    return AsyncMongoMockClient()["test"]


def _target() -> ResumeTarget:
    return ResumeTarget(target_title="後端工程師", resume_text="Python")


async def test_create_and_get(db):
    repo = SearchRepository(db)
    run = await repo.create("u1", "python", _target())
    assert run.search_id
    got = await repo.get(run.search_id)
    assert got is not None
    assert got.keyword == "python"
    assert got.user == "u1"


async def test_list_sorted_desc(db):
    repo = SearchRepository(db)
    a = await repo.create("u1", "first", _target())
    b = await repo.create("u1", "second", _target())
    await repo.create("u2", "other", _target())
    runs = await repo.list("u1")
    assert [r.search_id for r in runs] == [b.search_id, a.search_id]  # 新到舊


async def test_advance_updates_offset_and_count(db):
    repo = SearchRepository(db)
    run = await repo.create("u1", "python", _target())
    await repo.advance(run.search_id, next_offset=5, count_delta=3)
    await repo.advance(run.search_id, next_offset=10, count_delta=2)
    got = await repo.get(run.search_id)
    assert got.next_offset == 10
    assert got.count == 5


async def test_delete_cascades_matches(db):
    from job_tracker.db.repositories import MatchRepository
    from job_tracker.schemas import Job, JobMatch
    search_repo = SearchRepository(db)
    match_repo = MatchRepository(db)
    run = await search_repo.create("u1", "python", _target())
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://x/1")
    await match_repo.set_match(run.search_id, "u1",
                               JobMatch(job=job, score=80, reasons=["r"], gaps=["g"]))
    await search_repo.delete(run.search_id)
    assert await search_repo.get(run.search_id) is None
    assert await match_repo.list_by_search(run.search_id) == []
```

注意：`test_delete_cascades_matches` 依賴 Task 3 的 `MatchRepository.set_match(search_id, user, match)` 與 `list_by_search`。若 Task 3 尚未完成，先跳過此測試（標 `@pytest.mark.skip`），於 Task 3 完成後移除 skip。

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_search_repository.py -v`
Expected: FAIL — `ImportError: cannot import name 'SearchRepository'`

- [ ] **Step 3: 實作 SearchRepository**

在 `repositories.py` 頂部 import 補上 `from uuid import uuid4` 與 schema 的 `ResumeTarget, SearchRun`，新增類別：

```python
class SearchRepository:
    """搜尋歷史（每次「爬取並分析」一筆）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["searches"]
        self._matches = db["matches"]

    async def create(self, user: str, keyword: str, target: ResumeTarget) -> SearchRun:
        run = SearchRun(search_id=uuid4().hex, user=user, keyword=keyword, target=target)
        doc = run.model_dump(mode="json")
        doc["_id"] = run.search_id
        await self._col.insert_one(doc)
        return run

    async def get(self, search_id: str) -> SearchRun | None:
        doc = await self._col.find_one({"_id": search_id})
        return SearchRun(**doc) if doc else None

    async def list(self, user: str) -> list[SearchRun]:
        cur = self._col.find({"user": user}).sort("created_at", -1)
        return [SearchRun(**doc) async for doc in cur]

    async def advance(self, search_id: str, next_offset: int, count_delta: int) -> None:
        await self._col.update_one(
            {"_id": search_id},
            {"$set": {"next_offset": next_offset}, "$inc": {"count": count_delta}},
        )

    async def delete(self, search_id: str) -> None:
        await self._col.delete_one({"_id": search_id})
        await self._matches.delete_many({"search_id": search_id})
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_search_repository.py -v`
Expected: PASS（cascade 測試若 Task 3 未完成則為 skipped）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_search_repository.py
git commit -m "feat(repo): 新增 SearchRepository（搜尋歷史 CRUD + cascade 刪除）"
```

---

## Task 3: MatchRepository 改造（綁 search_id）

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`
- Test: `backend/tests/test_job_repository.py`（改寫 match 相關測試）

**Interfaces:**
- Consumes: `JobMatch`（既有）
- Produces `MatchRepository`（改造後）：
  - `set_match(search_id:str, user:str, match:JobMatch) -> None`（`_id="{search_id}|{job_id}"`）
  - `list_by_search(search_id:str) -> list[JobMatch]`（score desc）
  - `get_match(search_id:str, job_id:str) -> JobMatch | None`
  - `set_cover_letter(search_id:str, job_id:str, text:str) -> None`
  - 移除 `clear`、移除舊 `list_matches(user)`

- [ ] **Step 1: 改寫測試**

把 `backend/tests/test_job_repository.py` 中 match 相關測試（`test_set_and_list_matches_sorted`、`test_matches_isolated_by_user`、`test_clear_removes_only_that_users_matches`、`test_set_cover_letter_persists_on_match`）整段替換為：

```python
async def test_set_and_list_by_search_sorted(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 60))
    await match_repo.set_match("s1", "u1", make_match("2", 90))
    matches = await match_repo.list_by_search("s1")
    assert [m.score for m in matches] == [90, 60]
    assert matches[0].job.job_id == "2"


async def test_matches_isolated_by_search(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 50))
    await match_repo.set_match("s2", "u1", make_match("2", 80))
    assert [m.job.job_id for m in await match_repo.list_by_search("s1")] == ["1"]
    assert [m.job.job_id for m in await match_repo.list_by_search("s2")] == ["2"]


async def test_get_match(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 70))
    m = await match_repo.get_match("s1", "1")
    assert m is not None and m.score == 70
    assert await match_repo.get_match("s1", "nope") is None


async def test_set_cover_letter_persists(match_repo: MatchRepository):
    await match_repo.set_match("s1", "u1", make_match("1", 70))
    await match_repo.set_cover_letter("s1", "1", "敬啟者，求職信內容。")
    m = await match_repo.get_match("s1", "1")
    assert m.cover_letter == "敬啟者，求職信內容。"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_job_repository.py -v`
Expected: FAIL — `list_by_search` / `get_match` 不存在或簽名不符

- [ ] **Step 3: 改造 MatchRepository**

把 `repositories.py` 的 `MatchRepository` 改為：

```python
class MatchRepository:
    """契合度分析結果，綁定到一筆 search（_id = search_id|job_id）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["matches"]

    async def set_match(self, search_id: str, user: str, match: JobMatch) -> None:
        doc = match.model_dump(mode="json")
        doc["search_id"] = search_id
        doc["user"] = user
        doc["job_id"] = match.job.job_id
        await self._col.update_one(
            {"_id": f"{search_id}|{match.job.job_id}"}, {"$set": doc}, upsert=True
        )

    async def list_by_search(self, search_id: str) -> list[JobMatch]:
        matches = [
            JobMatch(**doc) async for doc in self._col.find({"search_id": search_id})
        ]
        return sorted(matches, key=lambda m: m.score, reverse=True)

    async def get_match(self, search_id: str, job_id: str) -> JobMatch | None:
        doc = await self._col.find_one({"_id": f"{search_id}|{job_id}"})
        return JobMatch(**doc) if doc else None

    async def set_cover_letter(self, search_id: str, job_id: str, text: str) -> None:
        await self._col.update_one(
            {"_id": f"{search_id}|{job_id}"}, {"$set": {"cover_letter": text}}
        )
```

- [ ] **Step 4: 跑測試確認通過 + 解除 Task 2 cascade skip**

Run: `cd backend && uv run pytest tests/test_job_repository.py tests/test_search_repository.py -v`
若 Task 2 的 `test_delete_cascades_matches` 之前標了 skip，移除 skip 後一起跑。
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_job_repository.py
git commit -m "refactor(repo): MatchRepository 綁定 search_id，移除 user 級 clear"
```

---

## Task 4: ApplicationRepository

**Files:**
- Modify: `backend/src/job_tracker/db/repositories.py`
- Test: `backend/tests/test_application_repository.py`（新建）

**Interfaces:**
- Consumes: `Application`, `ApplicationStatus`, `Job`（Task 1）
- Produces `ApplicationRepository`：
  - `add(app:Application) -> Application`（以 `user|job_id` 去重；已存在回現有，不覆蓋）
  - `list(user:str) -> list[Application]`（created_at desc）
  - `get(user:str, job_id:str) -> Application | None`
  - `set_status(user:str, job_id:str, status:ApplicationStatus) -> Application | None`（append 一筆 status event、更新 updated_at）
  - `remove(user:str, job_id:str) -> None`

- [ ] **Step 1: 寫失敗測試**

```python
# backend/tests/test_application_repository.py
import pytest
from mongomock_motor import AsyncMongoMockClient

from job_tracker.db.repositories import ApplicationRepository
from job_tracker.schemas import Application, ApplicationStatus, Job


@pytest.fixture
def repo():
    return ApplicationRepository(AsyncMongoMockClient()["test"])


def _app(user="u1", job_id="1", cover=None) -> Application:
    job = Job(job_id=job_id, code=f"c{job_id}", title="工程師", company="某公司",
              url=f"https://www.104.com.tw/job/c{job_id}")
    return Application(user=user, job_id=job_id, job=job,
                       source_search_id="s1", cover_letter=cover)


async def test_add_and_list(repo: ApplicationRepository):
    await repo.add(_app(cover="信"))
    apps = await repo.list("u1")
    assert len(apps) == 1
    assert apps[0].job_id == "1"
    assert apps[0].status == ApplicationStatus.TO_APPLY
    assert apps[0].cover_letter == "信"


async def test_add_is_deduped(repo: ApplicationRepository):
    await repo.add(_app(cover="原信"))
    await repo.add(_app(cover="新信"))  # 同 user|job_id → 不重複、不覆蓋
    apps = await repo.list("u1")
    assert len(apps) == 1
    assert apps[0].cover_letter == "原信"


async def test_list_isolated_by_user(repo: ApplicationRepository):
    await repo.add(_app(user="u1", job_id="1"))
    await repo.add(_app(user="u2", job_id="2"))
    assert [a.job_id for a in await repo.list("u1")] == ["1"]


async def test_set_status_appends_event(repo: ApplicationRepository):
    await repo.add(_app())
    updated = await repo.set_status("u1", "1", ApplicationStatus.APPLIED)
    assert updated.status == ApplicationStatus.APPLIED
    assert len(updated.events) == 1
    assert updated.events[0].type == "status"
    assert "applied" in updated.events[0].note


async def test_set_status_missing_returns_none(repo: ApplicationRepository):
    assert await repo.set_status("u1", "nope", ApplicationStatus.APPLIED) is None


async def test_remove(repo: ApplicationRepository):
    await repo.add(_app())
    await repo.remove("u1", "1")
    assert await repo.list("u1") == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_application_repository.py -v`
Expected: FAIL — `ImportError: cannot import name 'ApplicationRepository'`

- [ ] **Step 3: 實作 ApplicationRepository**

import 補 `Application, ApplicationEvent, ApplicationStatus`。新增類別：

```python
class ApplicationRepository:
    """求職追蹤清單（以 user|job_id 去重）。"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db["applications"]

    @staticmethod
    def _id(user: str, job_id: str) -> str:
        return f"{user}|{job_id}"

    async def add(self, app: Application) -> Application:
        _id = self._id(app.user, app.job_id)
        existing = await self._col.find_one({"_id": _id})
        if existing:
            return Application(**existing)  # 去重：已在追蹤就回現有
        doc = app.model_dump(mode="json")
        doc["_id"] = _id
        await self._col.insert_one(doc)
        return app

    async def list(self, user: str) -> list[Application]:
        cur = self._col.find({"user": user}).sort("created_at", -1)
        return [Application(**doc) async for doc in cur]

    async def get(self, user: str, job_id: str) -> Application | None:
        doc = await self._col.find_one({"_id": self._id(user, job_id)})
        return Application(**doc) if doc else None

    async def set_status(
        self, user: str, job_id: str, status: ApplicationStatus
    ) -> Application | None:
        ev = ApplicationEvent(type="status", note=f"→ {status.value}")
        now = ev.ts
        res = await self._col.update_one(
            {"_id": self._id(user, job_id)},
            {
                "$set": {"status": status.value, "updated_at": now.isoformat()},
                "$push": {"events": ev.model_dump(mode="json")},
            },
        )
        if res.matched_count == 0:
            return None
        return await self.get(user, job_id)

    async def remove(self, user: str, job_id: str) -> None:
        await self._col.delete_one({"_id": self._id(user, job_id)})
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd backend && uv run pytest tests/test_application_repository.py -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/db/repositories.py backend/tests/test_application_repository.py
git commit -m "feat(repo): 新增 ApplicationRepository（追蹤清單，去重 + 狀態事件）"
```

---

## Task 5: analyze 服務改以 search_id 寫入

**Files:**
- Modify: `backend/src/job_tracker/services/analyze.py`
- Test: `backend/tests/test_analyze_service.py`（若存在則改；否則於 router 測試覆蓋）

**Interfaces:**
- Consumes: `MatchRepository.set_match(search_id, user, match)`（Task 3）
- Produces: `analyze_jobs(search_id:str, user:str, keyword:str, target:ResumeTarget, job_repo, match_repo, *, offset=0, limit=5, ...) -> list[JobMatch]`

- [ ] **Step 1: 確認既有 analyze 測試**

Run: `grep -rln "analyze_jobs" backend/tests`。若有測試檔，於 Step 2 調整其呼叫加上 `search_id` 並把 `set_match` 斷言改為帶 search_id。若無，跳過測試調整（由 Task 6 router 測試覆蓋），但仍需在本 task 改實作簽名。

- [ ] **Step 2: 改實作簽名與寫入**

在 `analyze.py` 把函式簽名第一參數加 `search_id`，並把 `set_match` 呼叫改帶 `search_id`/`user`：

```python
async def analyze_jobs(
    search_id: str,
    user: str,
    keyword: str,
    target: ResumeTarget,
    job_repo: JobRepository,
    match_repo: MatchRepository,
    *,
    offset: int = 0,
    limit: int = 5,
    http_client: httpx.AsyncClient | None = None,
    llm_client=None,
    min_delay: float = 2.0,
    max_delay: float = 5.0,
) -> list[JobMatch]:
```

把 `await match_repo.set_match(user, match)` 改為：

```python
                await match_repo.set_match(search_id, user, match)
```

其餘邏輯（累積分頁、視窗、節流、容錯、排序）不變。

- [ ] **Step 3: 跑全測試確認沒打壞**

Run: `cd backend && uv run pytest -v`
Expected: 既有 jobs router 測試此時會 FAIL（因端點尚未改），這些於 Task 6 修正。analyze 直接呼叫的測試（若有）應 PASS。記錄哪些 FAIL 來自 Task 6 範圍。

- [ ] **Step 4: Commit**

```bash
git add backend/src/job_tracker/services/analyze.py backend/tests/
git commit -m "refactor(analyze): analyze_jobs 以 search_id 寫入 match"
```

---

## Task 6: deps + jobs router 改為 searches 端點

**Files:**
- Modify: `backend/src/job_tracker/api/deps.py`
- Modify: `backend/src/job_tracker/api/routers/jobs.py`
- Test: `backend/tests/test_jobs_api.py`（改寫）

**Interfaces:**
- Consumes: `SearchRepository`, `MatchRepository`, `analyze_jobs`（前述 task）
- Produces（deps）：`get_search_repo() -> SearchRepository`、`get_application_repo() -> ApplicationRepository`
- Produces（端點，prefix `/jobs`）：
  - `POST /searches` body `{keyword, target}` → `{"search_id": str, "matches": list[JobMatch]}`
  - `POST /searches/{search_id}/next` → `list[JobMatch]`
  - `GET /searches` → `list[SearchRun]`
  - `GET /searches/{search_id}/matches` → `list[JobMatch]`
  - `DELETE /searches/{search_id}` → `{"ok": True}`
  - `POST /searches/{search_id}/cover-letter` body `{job_id}` → `{"cover_letter": str}`

- [ ] **Step 1: 加 deps providers**

在 `deps.py` import 補 `SearchRepository, ApplicationRepository`，`__all__` 補兩個名稱，新增：

```python
def get_search_repo() -> SearchRepository:
    return SearchRepository(get_db())


def get_application_repo() -> ApplicationRepository:
    return ApplicationRepository(get_db())
```

- [ ] **Step 2: 寫失敗測試（改寫 test_jobs_api.py）**

整檔替換為：

```python
import asyncio

from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.api.routers import jobs as jobs_router
from job_tracker.db.repositories import (
    JobRepository,
    MatchRepository,
    QuotaRepository,
    SearchRepository,
)
from job_tracker.main import app
from job_tracker.schemas import Job, JobMatch


def make_job(job_id: str, code: str) -> Job:
    return Job(job_id=job_id, code=code, title="工程師", company="某公司",
               url=f"https://www.104.com.tw/job/{code}")


def _match(job_id: str, score: int) -> JobMatch:
    return JobMatch(job=make_job(job_id, f"c{job_id}"), score=score,
                    reasons=["r"], gaps=["g"])


_PAYLOAD = {
    "keyword": "python",
    "target": {"target_title": "後端工程師", "expected_salary": 70000,
               "resume_text": "Python"},
}


def _wire(db, monkeypatch, fake):
    monkeypatch.setattr(jobs_router, "analyze_jobs", fake)
    app.dependency_overrides[deps.get_job_repo] = lambda: JobRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_quota_repo] = lambda: QuotaRepository(db)


def test_create_search_returns_id_and_matches(monkeypatch):
    db = AsyncMongoMockClient()["test"]

    async def fake(search_id, user, keyword, target, job_repo, match_repo, **kw):
        return [_match("9", 88), _match("8", 70)]

    _wire(db, monkeypatch, fake)
    try:
        resp = TestClient(app).post("/api/jobs/searches", json=_PAYLOAD)
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["search_id"]
    assert body["matches"][0]["score"] == 88
    # 計入額度（2 筆）
    assert asyncio.run(QuotaRepository(db).used_today("dev@local")) == 2
    # search 已建立並推進 offset
    run = asyncio.run(SearchRepository(db).get(body["search_id"]))
    assert run.next_offset == 5
    assert run.count == 2


def test_list_and_get_search_matches(monkeypatch):
    db = AsyncMongoMockClient()["test"]

    async def fake(search_id, user, keyword, target, job_repo, match_repo, **kw):
        await match_repo.set_match(search_id, user, _match("9", 88))
        return [_match("9", 88)]

    _wire(db, monkeypatch, fake)
    try:
        client = TestClient(app)
        sid = client.post("/api/jobs/searches", json=_PAYLOAD).json()["search_id"]
        searches = client.get("/api/jobs/searches").json()
        matches = client.get(f"/api/jobs/searches/{sid}/matches").json()
    finally:
        app.dependency_overrides.clear()

    assert [s["search_id"] for s in searches] == [sid]
    assert matches[0]["job"]["job_id"] == "9"


def test_delete_search(monkeypatch):
    db = AsyncMongoMockClient()["test"]

    async def fake(search_id, user, keyword, target, job_repo, match_repo, **kw):
        return []

    _wire(db, monkeypatch, fake)
    try:
        client = TestClient(app)
        sid = client.post("/api/jobs/searches", json=_PAYLOAD).json()["search_id"]
        resp = client.delete(f"/api/jobs/searches/{sid}")
        searches = client.get("/api/jobs/searches").json()
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert searches == []
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_jobs_api.py -v`
Expected: FAIL — `/api/jobs/searches` 404（端點未建）

- [ ] **Step 4: 改寫 jobs router**

把 `jobs.py` 改為（移除舊 `/analyze`、`/matches`；保留 `GET ""` 列出 jobs 可留可刪，這裡保留）：

```python
"""職缺端點：搜尋歷史（search runs）+ 契合度分析 + 求職信。需登入、受每日額度限制。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user,
    ensure_quota,
    get_job_repo,
    get_match_repo,
    get_quota_repo,
    get_search_repo,
)
from job_tracker.db.repositories import (
    JobRepository,
    MatchRepository,
    QuotaRepository,
    SearchRepository,
)
from job_tracker.schemas import JobMatch, ResumeTarget, SearchRun
from job_tracker.services import cover_letter as cover_letter_svc
from job_tracker.services.analyze import analyze_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])

_BATCH = 5  # 每批分析筆數


class CreateSearchRequest(BaseModel):
    keyword: str
    target: ResumeTarget


class CoverLetterRequest(BaseModel):
    job_id: str


async def _ensure_owned(search_id: str, user: str, search_repo: SearchRepository) -> SearchRun:
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
    quota: QuotaRepository = Depends(get_quota_repo),
) -> dict:
    """開一筆新搜尋並分析第一批。"""
    await ensure_quota(user, quota)
    run = await search_repo.create(user, req.keyword, req.target)
    matches = await analyze_jobs(
        run.search_id, user, req.keyword, req.target, job_repo, match_repo,
        offset=0, limit=_BATCH,
    )
    await search_repo.advance(run.search_id, next_offset=_BATCH, count_delta=len(matches))
    await quota.add(user, len(matches))
    return {"search_id": run.search_id, "matches": matches}


@router.post("/searches/{search_id}/next")
async def next_batch(
    search_id: str,
    user: str = Depends(current_user),
    job_repo: JobRepository = Depends(get_job_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> list[JobMatch]:
    """在既有搜尋上續抓下一批（沿用當時 keyword/target）。"""
    run = await _ensure_owned(search_id, user, search_repo)
    await ensure_quota(user, quota)
    matches = await analyze_jobs(
        run.search_id, user, run.keyword, run.target, job_repo, match_repo,
        offset=run.next_offset, limit=_BATCH,
    )
    await search_repo.advance(
        run.search_id, next_offset=run.next_offset + _BATCH, count_delta=len(matches)
    )
    await quota.add(user, len(matches))
    return matches


@router.get("/searches")
async def list_searches(
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[SearchRun]:
    return await search_repo.list(user)


@router.get("/searches/{search_id}/matches")
async def search_matches(
    search_id: str,
    user: str = Depends(current_user),
    match_repo: MatchRepository = Depends(get_match_repo),
    search_repo: SearchRepository = Depends(get_search_repo),
) -> list[JobMatch]:
    await _ensure_owned(search_id, user, search_repo)
    return await match_repo.list_by_search(search_id)


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
    """對該搜尋裡的某職缺生成求職信，存回 match。"""
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

Run: `cd backend && uv run pytest tests/test_jobs_api.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/api/deps.py backend/src/job_tracker/api/routers/jobs.py backend/tests/test_jobs_api.py
git commit -m "feat(api): jobs router 改為 searches 系列端點（歷史 CRUD + 求職信）"
```

---

## Task 7: applications router 追蹤 CRUD

**Files:**
- Modify: `backend/src/job_tracker/api/routers/applications.py`
- Test: `backend/tests/test_applications_api.py`（改寫）

**Interfaces:**
- Consumes: `ApplicationRepository`, `SearchRepository`, `MatchRepository`, `ApplicationStatus`
- Produces（prefix `/applications`）：
  - `POST ""` body `{search_id, job_id}` → `Application`
  - `GET ""` → `list[Application]`
  - `PATCH /{job_id}` body `{status}` → `Application`
  - `DELETE /{job_id}` → `{"ok": True}`
  - 移除舊 `POST /cover-letter`（已移到 jobs/searches）

- [ ] **Step 1: 寫失敗測試（改寫 test_applications_api.py）**

整檔替換為：

```python
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from job_tracker.api import deps
from job_tracker.db.repositories import (
    ApplicationRepository,
    MatchRepository,
    SearchRepository,
)
from job_tracker.main import app
from job_tracker.schemas import Job, JobMatch, ResumeTarget


def _seed(db):
    """放一筆 search + match，供加入追蹤。"""
    import asyncio

    async def go():
        sr = SearchRepository(db)
        mr = MatchRepository(db)
        run = await sr.create("dev@local", "python",
                              ResumeTarget(target_title="後端", resume_text="x"))
        job = Job(job_id="1", code="c1", title="工程師", company="某公司",
                  url="https://www.104.com.tw/job/c1")
        await mr.set_match(run.search_id, "dev@local",
                           JobMatch(job=job, score=80, reasons=["r"], gaps=["g"],
                                    cover_letter="信"))
        return run.search_id

    return asyncio.run(go())


def _wire(db):
    app.dependency_overrides[deps.get_application_repo] = lambda: ApplicationRepository(db)
    app.dependency_overrides[deps.get_search_repo] = lambda: SearchRepository(db)
    app.dependency_overrides[deps.get_match_repo] = lambda: MatchRepository(db)


def test_add_list_update_delete_flow():
    db = AsyncMongoMockClient()["test"]
    sid = _seed(db)
    _wire(db)
    try:
        client = TestClient(app)
        added = client.post("/api/applications",
                            json={"search_id": sid, "job_id": "1"})
        listed = client.get("/api/applications")
        patched = client.patch("/api/applications/1", json={"status": "applied"})
        removed = client.delete("/api/applications/1")
        empty = client.get("/api/applications")
    finally:
        app.dependency_overrides.clear()

    assert added.status_code == 200
    assert added.json()["status"] == "to_apply"
    assert added.json()["cover_letter"] == "信"   # 求職信快照
    assert added.json()["job"]["company"] == "某公司"
    assert [a["job_id"] for a in listed.json()] == ["1"]
    assert patched.json()["status"] == "applied"
    assert len(patched.json()["events"]) == 1
    assert removed.status_code == 200
    assert empty.json() == []


def test_add_missing_match_is_404():
    db = AsyncMongoMockClient()["test"]
    sid = _seed(db)
    _wire(db)
    try:
        resp = TestClient(app).post("/api/applications",
                                    json={"search_id": sid, "job_id": "nope"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd backend && uv run pytest tests/test_applications_api.py -v`
Expected: FAIL — 端點未建（405/404）

- [ ] **Step 3: 改寫 applications router**

整檔替換為：

```python
"""求職追蹤清單端點（加入／看板列表／改狀態／移除）。需登入，不耗 LLM 額度。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user,
    get_application_repo,
    get_match_repo,
    get_search_repo,
)
from job_tracker.db.repositories import (
    ApplicationRepository,
    MatchRepository,
    SearchRepository,
)
from job_tracker.schemas import Application, ApplicationStatus

router = APIRouter(prefix="/applications", tags=["applications"])


class AddApplicationRequest(BaseModel):
    search_id: str
    job_id: str


class UpdateStatusRequest(BaseModel):
    status: ApplicationStatus


@router.post("")
async def add_application(
    req: AddApplicationRequest,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> Application:
    """把某搜尋裡的職缺加入追蹤清單（job 與求職信快照）。"""
    run = await search_repo.get(req.search_id)
    if run is None or run.user != user:
        raise HTTPException(status_code=404, detail="找不到該搜尋紀錄")
    match = await match_repo.get_match(req.search_id, req.job_id)
    if match is None:
        raise HTTPException(status_code=404, detail="找不到該職缺分析")
    app_obj = Application(
        user=user,
        job_id=req.job_id,
        job=match.job,
        source_search_id=req.search_id,
        cover_letter=match.cover_letter,
    )
    return await app_repo.add(app_obj)


@router.get("")
async def list_applications(
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> list[Application]:
    return await app_repo.list(user)


@router.patch("/{job_id}")
async def update_status(
    job_id: str,
    req: UpdateStatusRequest,
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> Application:
    updated = await app_repo.set_status(user, job_id, req.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="找不到該追蹤項目")
    return updated


@router.delete("/{job_id}")
async def remove_application(
    job_id: str,
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> dict:
    await app_repo.remove(user, job_id)
    return {"ok": True}
```

- [ ] **Step 4: 跑全測試確認通過**

Run: `cd backend && uv run pytest -v`
Expected: 全綠（含先前 task 的測試）。若有殘留引用 `cover_letter` 舊端點的測試，一併移除。

- [ ] **Step 5: Commit**

```bash
git add backend/src/job_tracker/api/routers/applications.py backend/tests/test_applications_api.py
git commit -m "feat(api): applications router 追蹤 CRUD，求職信端點移至 jobs/searches"
```

---

## Task 8: 前端 types + client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces（types）：`SearchRun`、`ApplicationStatus`、`ApplicationEvent`、`Application`
- Produces（client）：`createSearch`、`nextBatch`、`listSearches`、`searchMatches`、`deleteSearch`、`coverLetter`（改）、`addApplication`、`listApplications`、`updateApplicationStatus`、`removeApplication`

- [ ] **Step 1: 加型別**

在 `types/index.ts` 末尾加：

```typescript
export interface SearchRun {
  search_id: string;
  user: string;
  keyword: string;
  target: ResumeTarget;
  created_at: string;
  next_offset: number;
  count: number;
}

export type ApplicationStatus =
  | "to_apply"
  | "applied"
  | "interviewing"
  | "offer"
  | "closed";

export interface ApplicationEvent {
  ts: string;
  type: string;
  note: string;
}

export interface Application {
  user: string;
  job_id: string;
  job: Job;
  source_search_id: string;
  cover_letter?: string | null;
  status: ApplicationStatus;
  created_at: string;
  updated_at: string;
  events: ApplicationEvent[];
}
```

- [ ] **Step 2: 改 client**

在 `client.ts`：import 補 `Application`, `ApplicationStatus`, `SearchRun`。把 `listMatches`、`analyzeJobs`、`coverLetter` 三個方法移除，改為下列方法（其餘 parseResume/diagnose/usage/quota 不動）：

```typescript
  createSearch: (req: { keyword: string; target: ResumeTarget }) =>
    request<{ search_id: string; matches: JobMatch[] }>("/jobs/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  nextBatch: (searchId: string) =>
    request<JobMatch[]>(`/jobs/searches/${searchId}/next`, { method: "POST" }),
  listSearches: () => request<SearchRun[]>("/jobs/searches"),
  searchMatches: (searchId: string) =>
    request<JobMatch[]>(`/jobs/searches/${searchId}/matches`),
  deleteSearch: (searchId: string) =>
    request<{ ok: boolean }>(`/jobs/searches/${searchId}`, { method: "DELETE" }),
  coverLetter: (req: { search_id: string; job_id: string }) =>
    request<{ cover_letter: string }>(
      `/jobs/searches/${req.search_id}/cover-letter`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: req.job_id }),
      }
    ),
  addApplication: (req: { search_id: string; job_id: string }) =>
    request<Application>("/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  listApplications: () => request<Application[]>("/applications"),
  updateApplicationStatus: (jobId: string, status: ApplicationStatus) =>
    request<Application>(`/applications/${jobId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  removeApplication: (jobId: string) =>
    request<{ ok: boolean }>(`/applications/${jobId}`, { method: "DELETE" }),
```

刪除頂部不再使用的 `AnalyzeRequest` interface。

- [ ] **Step 3: 型別檢查**

Run: `cd frontend && npx tsc -b`
Expected: 會因 `JobList.tsx` 仍引用舊 `api.analyzeJobs`/`listMatches` 而報錯 —— 這些在 Task 9 修正。本 step 僅確認 `client.ts`/`types` 自身語法無誤（錯誤只應來自 JobList.tsx）。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/api/client.ts
git commit -m "feat(fe): 新增 searches/applications 型別與 API client 方法"
```

---

## Task 9: 前端 JobList — 歷史 chips + 加入追蹤鈕

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`

**Interfaces:**
- Consumes: `api.createSearch/nextBatch/listSearches/searchMatches/deleteSearch/coverLetter/addApplication/listApplications`

- [ ] **Step 1: 改 JobList 主體（歷史狀態 + chips）**

把 `JobList` 元件改為以 `selectedId` 驅動：

```tsx
export function JobList() {
  const { target } = useResume();
  const [keyword, setKeyword] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [noMore, setNoMore] = useState(false);
  const qc = useQueryClient();

  const searchesQ = useQuery({ queryKey: ["searches"], queryFn: api.listSearches });
  const matchesQ = useQuery({
    queryKey: ["search-matches", selectedId],
    queryFn: () => api.searchMatches(selectedId!),
    enabled: !!selectedId,
  });

  const createMut = useMutation({
    mutationFn: api.createSearch,
    onSuccess: (data) => {
      setSelectedId(data.search_id);
      setNoMore(data.matches.length === 0);
      qc.invalidateQueries({ queryKey: ["searches"] });
      qc.invalidateQueries({ queryKey: ["search-matches", data.search_id] });
    },
  });
  const nextMut = useMutation({
    mutationFn: () => api.nextBatch(selectedId!),
    onSuccess: (data) => {
      setNoMore(data.length === 0);
      qc.invalidateQueries({ queryKey: ["search-matches", selectedId] });
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
  });
  const delMut = useMutation({
    mutationFn: api.deleteSearch,
    onSuccess: (_d, sid) => {
      if (sid === selectedId) setSelectedId(null);
      qc.invalidateQueries({ queryKey: ["searches"] });
    },
  });

  const busy = createMut.isPending || nextMut.isPending;
  const canRun = !!target && keyword.trim().length > 0 && !busy;
  const run = () => {
    if (target) {
      setNoMore(false);
      createMut.mutate({ keyword: keyword.trim(), target });
    }
  };
  const runNext = () => !busy && selectedId && nextMut.mutate();

  const searches = searchesQ.data ?? [];
  const matches = matchesQ.data ?? [];
```

- [ ] **Step 2: 歷史 chips UI（控制列下方）**

在控制列 panel 之後、結果 panel 之前插入歷史列：

```tsx
          {searches.length > 0 && (
            <div className="jt-panel" style={{ marginBottom: 20 }}>
              <div className="jt-panel-body">
                <Group gap={8} wrap="wrap">
                  {searches.map((s) => (
                    <Group
                      key={s.search_id}
                      gap={4}
                      wrap="nowrap"
                      px={10}
                      py={6}
                      onClick={() => setSelectedId(s.search_id)}
                      style={{
                        cursor: "pointer",
                        borderRadius: 8,
                        border: "1px solid var(--jt-border)",
                        background:
                          s.search_id === selectedId
                            ? "var(--jt-teal-dim, rgba(52,214,200,0.12))"
                            : "transparent",
                      }}
                    >
                      <Text fz="xs">
                        {s.keyword} ·{" "}
                        {new Date(s.created_at).toLocaleString("zh-TW", {
                          month: "numeric",
                          day: "numeric",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}{" "}
                        · {s.count} 筆
                      </Text>
                      <Text
                        fz="xs"
                        c="dimmed"
                        onClick={(e) => {
                          e.stopPropagation();
                          delMut.mutate(s.search_id);
                        }}
                        style={{ cursor: "pointer" }}
                      >
                        ✕
                      </Text>
                    </Group>
                  ))}
                </Group>
              </div>
            </div>
          )}
```

- [ ] **Step 3: 結果區標題列的「分析下一批」改用 selectedId/nextMut**

把結果 panel-head 內的下一批按鈕條件由 `offset > 0` 改為 `!!selectedId`，loading 與停用改用 `busy`/`canRun`，並把 `analyzeMut.isPending` 改為 `busy`。把 MatchCard 呼叫補上 `searchId={selectedId!}`。

- [ ] **Step 4: MatchCard 改 props + 求職信 + 加入追蹤**

MatchCard 簽名改 `{ match, searchId }`，求職信改 `api.coverLetter({ search_id: searchId, job_id: job.job_id })`，並在 modal 完成區塊加「加入追蹤」鈕：

```tsx
function MatchCard({ match, searchId }: { match: JobMatch; searchId: string }) {
  const { job } = match;
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  const [draft, setDraft] = useState(match.cover_letter ?? "");
  const hasLetter = !!draft;

  const appsQ = useQuery({ queryKey: ["applications"], queryFn: api.listApplications });
  const tracked = (appsQ.data ?? []).some((a) => a.job_id === job.job_id);

  const letterMut = useMutation({
    mutationFn: () => api.coverLetter({ search_id: searchId, job_id: job.job_id }),
    onSuccess: (d) => {
      setDraft(d.cover_letter);
      qc.invalidateQueries({ queryKey: ["search-matches", searchId] });
    },
  });
  const trackMut = useMutation({
    mutationFn: () => api.addApplication({ search_id: searchId, job_id: job.job_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
```

在求職信 modal 完成狀態的 `Group justify="flex-end"` 內，最前面加：

```tsx
              <Button
                variant="light"
                color="teal"
                disabled={tracked || trackMut.isPending}
                onClick={() => trackMut.mutate()}
              >
                {tracked ? "✓ 已在追蹤清單" : "加入追蹤"}
              </Button>
```

（其餘 modal/卡片結構沿用現有，只替換上述呼叫與按鈕；移除舊的 `generate`/`openLetter` 對 `target`/`letterMut.mutate({target,...})` 的依賴，改用上面的 `letterMut`。）

- [ ] **Step 5: 建置驗證**

Run: `cd frontend && npm run build`
Expected: build 成功，無 TS 錯誤。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(fe): JobList 歷史 chips 切換、續抓改 search、求職信加入追蹤鈕"
```

---

## Task 10: 前端 Applications 看板頁 + 路由

**Files:**
- Create: `frontend/src/pages/Applications.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `api.listApplications`, `api.updateApplicationStatus`, `api.removeApplication`

- [ ] **Step 1: 建看板頁**

```tsx
// frontend/src/pages/Applications.tsx
import { Box, Group, Select, Stack, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Application, ApplicationStatus } from "../types";

const COLUMNS: { status: ApplicationStatus; label: string }[] = [
  { status: "to_apply", label: "待投遞" },
  { status: "applied", label: "已投遞" },
  { status: "interviewing", label: "面試中" },
  { status: "offer", label: "Offer" },
  { status: "closed", label: "結束" },
];

export function Applications() {
  const appsQ = useQuery({ queryKey: ["applications"], queryFn: api.listApplications });
  const apps = appsQ.data ?? [];

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1400} mx="auto">
      <Stack gap={6} mb={28}>
        <span className="jt-eyebrow">求職 <b>×</b> 追蹤</span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          追蹤清單
        </Title>
        <Text c="dimmed" fz="sm">把職缺加入後，在這裡管理投遞與面試進度。</Text>
      </Stack>

      <Group align="flex-start" gap={14} wrap="nowrap" style={{ overflowX: "auto" }}>
        {COLUMNS.map((col) => {
          const items = apps.filter((a) => a.status === col.status);
          return (
            <div key={col.status} className="jt-panel" style={{ minWidth: 260, flex: 1 }}>
              <div className="jt-panel-head">
                <span className="jt-eyebrow">{col.label} · {items.length}</span>
              </div>
              <div className="jt-panel-body">
                <Stack gap={10}>
                  {items.length === 0 ? (
                    <Text fz="xs" c="dimmed">—</Text>
                  ) : (
                    items.map((a) => <AppCard key={a.job_id} app={a} />)
                  )}
                </Stack>
              </div>
            </div>
          );
        })}
      </Group>
    </Box>
  );
}

function AppCard({ app }: { app: Application }) {
  const qc = useQueryClient();
  const statusMut = useMutation({
    mutationFn: (status: ApplicationStatus) =>
      api.updateApplicationStatus(app.job_id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
  const removeMut = useMutation({
    mutationFn: () => api.removeApplication(app.job_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  return (
    <div className="jt-jobcard">
      <Group justify="space-between" wrap="nowrap" mb={6}>
        <a className="jt-job-title" href={app.job.url} target="_blank" rel="noreferrer">
          {app.job.title}
        </a>
        <Text fz="xs" c="dimmed" style={{ cursor: "pointer" }} onClick={() => removeMut.mutate()}>
          ✕
        </Text>
      </Group>
      <div className="jt-job-meta">{app.job.company}</div>
      <Select
        mt={8}
        size="xs"
        value={app.status}
        data={COLUMNS.map((c) => ({ value: c.status, label: c.label }))}
        onChange={(v) => v && statusMut.mutate(v as ApplicationStatus)}
        allowDeselect={false}
      />
    </div>
  );
}
```

- [ ] **Step 2: 接路由與導覽**

在 `App.tsx`：import `Applications`；`NAV` 加 `{ to: "/applications", label: "追蹤清單", tag: "03" }`；`Routes` 加 `<Route path="/applications" element={<Applications />} />`。

- [ ] **Step 3: 建置驗證**

Run: `cd frontend && npm run build`
Expected: build 成功。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Applications.tsx frontend/src/App.tsx
git commit -m "feat(fe): 新增追蹤清單五欄看板頁與導覽入口"
```

---

## Task 11: 端對端煙霧測試 + 文件更新

**Files:**
- Modify: `docs/PROGRESS.md`

- [ ] **Step 1: 後端全測試**

Run: `cd backend && uv run pytest -v`
Expected: 全綠。

- [ ] **Step 2: 啟動服務手動驗證流程**

殺掉殘留 8000 埠進程後啟動後端與前端，用 Playwright（webapp-testing skill）或手動驗證：
1. 新搜尋 → 出現一筆歷史 chip、結果列出
2. 「分析下一批」→ 同一 chip 筆數增加、不清空舊結果
3. 再新搜尋 → 多一筆歷史 chip，可切換回前一筆看到原結果
4. 生成求職信 → modal 出現「加入追蹤」→ 點擊後到 `/applications` 看板「待投遞」欄出現該卡
5. 改狀態下拉 → 卡片移動到對應欄
6. 刪除歷史 chip → 該 search 結果消失，追蹤清單中已加入的卡片仍在（快照）

- [ ] **Step 3: 更新 PROGRESS.md**

把「求職進度追蹤清單」狀態更新為「核心完成（歷史紀錄＋五欄看板）」，並記下個 sub-project：面試多輪時間軸、面試筆記、看板拖拉。

- [ ] **Step 4: Commit**

```bash
git add docs/PROGRESS.md
git commit -m "docs: 更新進度（搜尋歷史 + 追蹤清單核心完成）"
```

---

## Self-Review 註記

- **Spec 覆蓋**：search runs CRUD（T2/T6）、matches 綁 search_id（T3）、applications 去重＋狀態事件（T4/T7）、求職信改 search 端點（T6）、前端歷史切換（T9）、看板（T10）、加入追蹤銜接（T9 鈕 + T7 端點）皆有對應 task。
- **範圍切分**：面試多輪時間軸、筆記、看板拖拉明確留待下個 sub-project（events 資料骨架已備）。
- **型別一致**：跨 task 統一 `set_match(search_id, user, match)`、`list_by_search`、`get_match`、`advance(search_id, next_offset, count_delta)`、`add(app)`、`set_status(user, job_id, status)`、`createSearch/nextBatch/searchMatches`。
- **遷移**：舊 matches 結構直接作廢，無遷移腳本（dev 階段）。
