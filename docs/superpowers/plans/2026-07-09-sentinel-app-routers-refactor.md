# sentinel `web/app.py` → `web/routers/` 套件重構 實作計畫（階段 2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `src/career_sentinel/web/app.py`（619 行、38 條路由塞在單一 `create_app` 閉包）依領域拆成 `web/routers/` 套件的 6 個 `APIRouter` + 一個 `web/deps.py`，行為零改變，全程維持既有測試綠。

**Architecture:** 唯一的閉包狀態是資料庫路徑。作法：`create_app` 把 `resolved_db` 存進 `app.state.db_path`；`web/deps.py` 提供 FastAPI 依賴 `get_db_path(request)` 回傳該路徑；各 endpoint 搬到領域 router，簽名加 `db_path: str = Depends(get_db_path)`，並把原本的 `_conn()` 替換成 `store.connect(db_path)`（呼叫點與時機不變）。`create_app` 最終只負責：設 `app.state`、啟動 scheduler、`include_router` 六個 router、掛載 SPA 靜態檔。

**Tech Stack:** Python 3.12、FastAPI（APIRouter / Depends / Request）、pytest、既有 `career_sentinel` 模組。

## Global Constraints

- **行為零改變**：純結構搬移，不改任何執行期邏輯、回應格式、狀態碼、路由字串、連線建立時機。
- **路由字串保持原樣**：router 不設 `prefix`，各裝飾器維持完整 `/api/...` 路徑（與原 `@app.get("/api/...")` 逐字相同）。
- **連線建立方式**：`_conn()` → `store.connect(db_path)`，其中 `db_path` 由 `Depends(get_db_path)` 注入；`get_db_path(request)` 回傳 `request.app.state.db_path`。不引入 per-request 連線快取，維持「呼叫點才建連線」的原行為。
- **`create_app(db_path: str | None = None)` 簽名不得改**（測試以 `create_app(db_path=...)` 呼叫）。
- **SPA 靜態檔掛載必須在所有 router 之後**（`app.mount("/", StaticFiles(...))` 會吃掉未匹配路徑）。
- **scheduler 啟動保留在 `create_app`**：`scheduler.start(lambda: store.load_settings(store.connect(resolved_db)))`。
- **測試全程綠**：每個 task 後跑 `./.venv/Scripts/python.exe -m pytest -q`（工作目錄 `sentinel/`），維持 `400 passed`。
- **不新增行為測試**；唯一允許的測試改動見 Task 6（`webapp.pipeline` → 直接 patch `pipeline` 模組）。
- 匯入慣例：`web/routers/*.py` 與 `web/deps.py` 引用 `career_sentinel` 兄弟模組用 `from ... import X`（三點）、引用 `web` 兄弟模組用 `from .. import X`（兩點）、引用同套件用 `from .X import Y`。
- endpoint 本體內原有的 function-local import（如 `from ...scraper.search import fetch_search`、`from ...scraper import resume104 as r104`、`from ...scraper.recommend import recommend_session`）保留在函式內，逐字搬移（路徑點數依新位置調整為三點）。

---

## 搬移規則（worked example — 每個 endpoint 一律照此機械轉換）

原（在 `create_app` 內）：

```python
    @app.get("/api/settings")
    def get_settings() -> dict:
        return store.load_settings(_conn()).model_dump()
```

搬到 `web/routers/settings.py` 後：

```python
@router.get("/api/settings")
def get_settings(db_path: str = Depends(get_db_path)) -> dict:
    return store.load_settings(store.connect(db_path)).model_dump()
```

轉換動作僅有四項，其餘逐字不動：
1. `@app.<method>` → `@router.<method>`（路徑字串不變）。
2. 若函式本體用到連線/資料庫路徑，簽名加參數 `db_path: str = Depends(get_db_path)`（加在既有參數之後）。
3. 函式本體每個 `_conn()` → `store.connect(db_path)`。
4. `scrape` 特例：`runner.default_scrape(resolved_db)` → `runner.default_scrape(db_path)`。

**不需要 db 的 endpoint（不加 `db_path` 參數）**：`status`、`schedule`、`schedule_ack`、`apply_open`。其餘皆需。

---

## 檔案結構（階段 2 終態）

```
src/career_sentinel/web/
├─ app.py            # 只剩 create_app：設 app.state、起 scheduler、include 6 routers、掛 SPA
├─ deps.py           # get_db_path(request)
├─ runner.py         # （不動）
├─ scheduler.py      # （不動）
├─ apply.py          # （不動）
└─ routers/
   ├─ __init__.py    # 空
   ├─ dashboard.py   # snapshot/scrape/status/usage/schedule + _snapshot_payload
   ├─ settings.py    # settings/preferences
   ├─ resume.py      # resume upload/diagnose/import104/get
   ├─ jobs.py        # match/tailor/apply-open/negotiate/search/recommend/job/research + _MatchReq/_NegotiateReq
   ├─ tracked.py     # tracked* + interviews dismiss/restore + _TrackReq/_InterviewsReq/_InterviewKeyReq
   └─ chat.py        # chat send/apply/get/clear/export/memory-delete + _ChatReq + _chat_events
```

---

### Task 1: `web/deps.py` + `app.state` + `settings` router

第一個 task 建立共用相依與套件骨架，並搬第一個最單純的領域（settings/preferences）當範式。

**Files:**
- Create: `src/career_sentinel/web/deps.py`
- Create: `src/career_sentinel/web/routers/__init__.py`（空檔）
- Create: `src/career_sentinel/web/routers/settings.py`
- Modify: `src/career_sentinel/web/app.py`（設 `app.state.db_path`、`scheduler.start` 改用 `store.connect(resolved_db)`、`include_router(settings.router)`、移除 4 個 settings/preferences endpoint）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Produces: `deps.get_db_path(request: Request) -> str`；`routers.settings.router: APIRouter`。後續 task 沿用 `get_db_path` 與相同的 router 模式。

- [ ] **Step 1: 建立 `web/deps.py`**

```python
"""共用相依：從 app.state 取得資料庫路徑供各 router 使用。"""
from __future__ import annotations

from fastapi import Request


def get_db_path(request: Request) -> str:
    return request.app.state.db_path
```

- [ ] **Step 2: 建立空的 `web/routers/__init__.py`**

用 Write 建立空檔（0 bytes 或僅一行套件 docstring）。

- [ ] **Step 3: 建立 `web/routers/settings.py`**

把 `app.py` 的 `get_settings`/`put_settings`/`get_preferences`/`put_preferences` 依搬移規則搬入：

```python
"""settings / preferences 路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ... import store
from ...models import JobPreferences, Settings
from ..deps import get_db_path

router = APIRouter()


@router.get("/api/settings")
def get_settings(db_path: str = Depends(get_db_path)) -> dict:
    return store.load_settings(store.connect(db_path)).model_dump()


@router.put("/api/settings")
def put_settings(settings: Settings, db_path: str = Depends(get_db_path)) -> dict:
    store.save_settings(store.connect(db_path), settings)
    return settings.model_dump()


@router.get("/api/preferences")
def get_preferences(db_path: str = Depends(get_db_path)) -> dict:
    return store.load_preferences(store.connect(db_path)).model_dump()


@router.put("/api/preferences")
def put_preferences(prefs: JobPreferences, db_path: str = Depends(get_db_path)) -> dict:
    store.save_preferences(store.connect(db_path), prefs)
    return prefs.model_dump()
```

- [ ] **Step 4: 修改 `create_app`**

在 `app.py` 的 `create_app` 內：
1. 在 `resolved_db = ...` 之後加一行 `app.state.db_path = resolved_db`。
2. 把 `scheduler.start(lambda: store.load_settings(_conn()))` 改成 `scheduler.start(lambda: store.load_settings(store.connect(resolved_db)))`。
3. 刪除這 4 個 endpoint（`get_settings`/`put_settings`/`get_preferences`/`put_preferences`）。
4. 在 `create_app` 內、SPA 掛載之前加入：`from .routers import settings`（放檔頭亦可）與 `app.include_router(settings.router)`。

（`_conn` helper 目前仍保留，供尚未搬移的 endpoint 使用。）

- [ ] **Step 5: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; create_app()"`
Expected: 無錯誤。

- [ ] **Step 6: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 7: Commit**

```bash
git add src/career_sentinel/web/deps.py src/career_sentinel/web/routers/__init__.py src/career_sentinel/web/routers/settings.py src/career_sentinel/web/app.py
git commit -m "refactor(sentinel): web/app.py 抽出 settings router + deps.get_db_path"
```

---

### Task 2: `resume` router

**Files:**
- Create: `src/career_sentinel/web/routers/resume.py`
- Modify: `src/career_sentinel/web/app.py`（移除 4 個 resume endpoint、加 include_router）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Consumes: `deps.get_db_path`。
- Produces: `routers.resume.router`。

- [ ] **Step 1: 建立 `web/routers/resume.py`**

把 `app.py` 的 `resume_upload`/`resume_diagnose`/`resume_import104`/`resume_get` 依搬移規則搬入。檔頭：

```python
"""resume 路由：上傳 / 健檢 / 從 104 匯入 / 讀取狀態。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ... import diagnosis, resume, store
from ..deps import get_db_path
from .. import runner

logger = logging.getLogger("career_sentinel.web")

router = APIRouter()
```

搬移細節：
- 這 4 個 endpoint 皆用到連線 → 全部加 `db_path: str = Depends(get_db_path)`（`resume_upload` 為 `async def`，參數加在 `file: UploadFile = File(...)` 之後）。
- 各 `_conn()` → `store.connect(db_path)`。
- `resume_import104` 內 `from ..scraper import resume104 as r104` → 改為 `from ...scraper import resume104 as r104`（保留在函式內）。
- 其餘本體逐字不動（含所有 HTTPException 狀態碼與訊息）。

- [ ] **Step 2: 修改 `create_app`**

刪除 `app.py` 內這 4 個 endpoint；加入 `from .routers import resume` 與 `app.include_router(resume.router)`（在 SPA 掛載之前）。

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; create_app()"`
Expected: 無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/web/routers/resume.py src/career_sentinel/web/app.py
git commit -m "refactor(sentinel): web/app.py 抽出 resume router"
```

---

### Task 3: `dashboard` router（含 `_snapshot_payload`）

**Files:**
- Create: `src/career_sentinel/web/routers/dashboard.py`
- Modify: `src/career_sentinel/web/app.py`（移除 `_snapshot_payload` 與 7 個 endpoint、加 include_router）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Consumes: `deps.get_db_path`。
- Produces: `routers.dashboard.router`。

- [ ] **Step 1: 建立 `web/routers/dashboard.py`**

把 `app.py` 模組層的 `_snapshot_payload(conn)` 函式**逐字**搬入本檔，並把這 7 個 endpoint 依搬移規則搬入：`snapshot`、`scrape`、`status`、`usage_summary`（GET /api/usage）、`usage_reset`（DELETE /api/usage）、`schedule`、`schedule_ack`。檔頭：

```python
"""dashboard 路由：快照 / 重新抓取 / 狀態 / 用量 / 排程。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ... import calendar_link, company_link, diff, digest, pipeline, store, usage as usagemod, watch
from ...models import interview_key
from ..deps import get_db_path
from .. import runner, scheduler

router = APIRouter()
```

搬移細節：
- `_snapshot_payload` 逐字搬入（本體不變；它以參數 `conn` 運作）。
- `snapshot` → 加 `db_path`，本體 `return _snapshot_payload(_conn())` → `return _snapshot_payload(store.connect(db_path))`。
- `scrape` → 加 `db_path`；`runner.default_scrape(resolved_db)` → `runner.default_scrape(db_path)`。
- `status`、`schedule`、`schedule_ack` → **不加** `db_path`（不用 db），本體逐字。
- `usage_summary`/`usage_reset` → 加 `db_path`，`_conn()` → `store.connect(db_path)`。

- [ ] **Step 2: 修改 `create_app`**

刪除 `app.py` 內模組層 `_snapshot_payload` 函式與這 7 個 endpoint；加入 `from .routers import dashboard` 與 `app.include_router(dashboard.router)`。

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; create_app()"`
Expected: 無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/web/routers/dashboard.py src/career_sentinel/web/app.py
git commit -m "refactor(sentinel): web/app.py 抽出 dashboard router（含 _snapshot_payload）"
```

---

### Task 4: `jobs` router（含 `_MatchReq`/`_NegotiateReq`）

**Files:**
- Create: `src/career_sentinel/web/routers/jobs.py`
- Modify: `src/career_sentinel/web/app.py`（移除 `_MatchReq`/`_NegotiateReq` 與 8 個 endpoint、加 include_router）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Consumes: `deps.get_db_path`。
- Produces: `routers.jobs.router`。

- [ ] **Step 1: 建立 `web/routers/jobs.py`**

把 `app.py` 模組層的 `_MatchReq`、`_NegotiateReq` 兩個 pydantic 類別**逐字**搬入本檔，並把這 8 個 endpoint 依搬移規則搬入：`match_job`（POST /api/match）、`tailor_job`（POST /api/tailor）、`apply_open`（POST /api/apply/open）、`negotiate_offer_ep`（POST /api/negotiate）、`search`（GET /api/search）、`recommend`（GET /api/recommend）、`job_by_url`（GET /api/job）、`research_get`（GET /api/research）。檔頭：

```python
"""jobs 路由：比對 / 客製化 / 開投遞頁 / 談判 / 搜尋 / 推薦 / 職缺詳情 / 公司評價。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import config, jobfetch, match, negotiate, pipeline, research, store, tailor, watch
from ...models import OfferDetail
from ..deps import get_db_path
from .. import apply, runner

logger = logging.getLogger("career_sentinel.web")

router = APIRouter()


class _MatchReq(BaseModel):
    job_url: str


class _NegotiateReq(BaseModel):
    code: str
```

搬移細節：
- `apply_open` → **不加** `db_path`（不用 db）。其餘 7 個都加 `db_path`。
- 各 `_conn()` → `store.connect(db_path)`。
- `search` 內 `from ..scraper.search import fetch_search` → `from ...scraper.search import fetch_search`（函式內保留）。
- `recommend` 內 `from ..scraper.recommend import recommend_session` → `from ...scraper.recommend import recommend_session`（函式內保留）。
- 其餘逐字（含所有狀態碼、`logger.exception(...)`、瀏覽器鎖 `runner.try_begin_browser()`/`runner.end_browser()`）。

- [ ] **Step 2: 修改 `create_app`**

刪除 `app.py` 內 `_MatchReq`、`_NegotiateReq` 與這 8 個 endpoint；加入 `from .routers import jobs` 與 `app.include_router(jobs.router)`。

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; create_app()"`
Expected: 無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/web/routers/jobs.py src/career_sentinel/web/app.py
git commit -m "refactor(sentinel): web/app.py 抽出 jobs router"
```

---

### Task 5: `tracked` router（含 `_TrackReq`/`_InterviewsReq`/`_InterviewKeyReq`）

**Files:**
- Create: `src/career_sentinel/web/routers/tracked.py`
- Modify: `src/career_sentinel/web/app.py`（移除 3 個 request model 與 9 個 endpoint、加 include_router）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Consumes: `deps.get_db_path`。
- Produces: `routers.tracked.router`。

- [ ] **Step 1: 建立 `web/routers/tracked.py`**

把 `app.py` 模組層的 `_TrackReq`、`_InterviewsReq`、`_InterviewKeyReq` **逐字**搬入，並把這 9 個 endpoint 依搬移規則搬入：`track_job`（POST /api/tracked）、`tracked_get`（GET /api/tracked/{code}）、`untrack_job`（DELETE /api/tracked/{code}）、`tracked_set_offer`（POST /api/tracked/{code}/offer）、`tracked_set_reject`（POST /api/tracked/{code}/reject）、`tracked_reset`（POST /api/tracked/{code}/reset）、`set_interviews_ep`（PUT /api/tracked/{code}/interviews）、`interviews_dismiss`（POST /api/interviews/dismiss）、`interviews_restore`（POST /api/interviews/restore）。檔頭：

```python
"""tracked 路由：追蹤管道狀態 / offer / 面試紀錄 / 面試邀約摺疊。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ... import store
from ...models import InterviewNote, OfferDetail
from ..deps import get_db_path

router = APIRouter()


class _TrackReq(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    match_score: int | None = None
    match_json: dict | None = None
    tailor_json: dict | None = None


class _InterviewKeyReq(BaseModel):
    key: str


class _InterviewsReq(BaseModel):
    notes: list[InterviewNote]
```

搬移細節：全部 9 個都用到連線 → 都加 `db_path: str = Depends(get_db_path)`（含路徑參數 `code: str` 的，`db_path` 加在其後）；各 `_conn()` → `store.connect(db_path)`；本體其餘逐字（含 `import json` 使用處——注意 `tracked_get` 用到 `json.loads`，故檔頭需 `import json`）。

修正上面檔頭：在 `from __future__` 之後加 `import json`（`tracked_get` 需要）。

- [ ] **Step 2: 修改 `create_app`**

刪除 `app.py` 內 `_TrackReq`、`_InterviewKeyReq`、`_InterviewsReq` 與這 9 個 endpoint；加入 `from .routers import tracked` 與 `app.include_router(tracked.router)`。

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; create_app()"`
Expected: 無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/web/routers/tracked.py src/career_sentinel/web/app.py
git commit -m "refactor(sentinel): web/app.py 抽出 tracked router"
```

---

### Task 6: `chat` router（含 `_ChatReq`/`_chat_events`）+ 更新 1 處測試 patch 目標

**Files:**
- Create: `src/career_sentinel/web/routers/chat.py`
- Modify: `src/career_sentinel/web/app.py`（移除 `_ChatReq`/`_chat_events` 與 6 個 endpoint、加 include_router）
- Modify: `tests/test_web_chat.py`（1 處 patch 目標）
- Test: 其餘 `tests/` 不改

**Interfaces:**
- Consumes: `deps.get_db_path`。
- Produces: `routers.chat.router`。

**為何要改測試：** `tests/test_web_chat.py:216` 目前 `monkeypatch.setattr(webapp.pipeline, "build_pipeline", …)` 透過 `app.py` 上的 `pipeline` 屬性 patch。本 task 把 `/api/chat` 搬到 chat router 後，`app.py` 不再 import `pipeline`，`webapp.pipeline` 會失效。因 patch 的其實是共享的 `pipeline` 模組物件，改成直接 patch 該模組即可（chat router 以 `from ... import pipeline` 呼叫 `pipeline.build_pipeline`，會看到 patch）。

- [ ] **Step 1: 建立 `web/routers/chat.py`**

把 `app.py` 模組層的 `_ChatReq`、`_chat_events(messages, system, db_path=None)` **逐字**搬入（`_chat_events` 本體不變），並把這 6 個 endpoint 依搬移規則搬入：`chat_send`（POST /api/chat）、`chat_apply`（POST /api/chat/apply）、`chat_get`（GET /api/chat）、`chat_clear`（DELETE /api/chat）、`export_md`（GET /api/export）、`memory_delete`（DELETE /api/memory/{index}）。檔頭：

```python
"""chat 路由：串流聊天 / 套用建議 / 讀取 / 清空 / 匯出 / 刪記憶。"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse

from ... import chat as chatmod, config, llm, pipeline, store, watch
from ...models import ChatMessage, ChatState, SuggestedUpdate
from ..deps import get_db_path

router = APIRouter()


class _ChatReq(BaseModel):
    message: str


def _chat_events(messages, system, db_path=None):
    """依 provider 產聊天事件流：foundry 走工具迴圈、openai 走既有純聊天。"""
    if config.llm_provider() == "foundry":
        yield from chatmod.stream_with_tools(messages, system=system, db_path=db_path)
    else:
        for chunk in llm.chat_stream(messages, system=system, feature="整理助手"):
            yield {"type": "text", "text": chunk}
```

修正：上面檔頭用到 `BaseModel`，請在 import 區加 `from pydantic import BaseModel`。

- [ ] **Step 2: 搬入 `chat_send`（串流；最需小心，此處給出完整轉換後程式）**

`chat_send` 原本用 `resolved_db` 傳進 generator。轉換後改用注入的 `db_path`，其餘邏輯逐字保留：

```python
@router.post("/api/chat")
def chat_send(req: _ChatReq, db_path: str = Depends(get_db_path)):
    if not config.llm_provider():
        raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
    conn = store.connect(db_path)
    try:
        pipe_summary = chatmod.format_pipeline_summary(pipeline.build_pipeline(conn))
    except Exception:
        pipe_summary = ""
    system = chatmod.build_system_prompt(
        store.load_resume(conn), store.load_settings(conn),
        store.load_preferences(conn), store.load_memory(conn), pipe_summary,
    )
    messages = chatmod.build_messages(store.load_chat(conn), req.message)
    settings_snapshot = store.load_settings(conn)

    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def gen():
        filt = chatmod.StreamFilter()
        clean_parts: list[str] = []
        try:
            for ev in _chat_events(messages, system, db_path):
                if ev["type"] == "jobs":
                    yield _sse("jobs", {
                        "keyword": ev["keyword"],
                        "items": [
                            {
                                "code": j.code, "url": j.url, "title": j.title,
                                "company": j.company, "salary": j.salary,
                                "is_watched": watch.is_watched(j.company, j.title, settings_snapshot),
                            }
                            for j in ev["items"]
                        ],
                    })
                    continue
                out = filt.feed(ev["text"])
                if out:
                    clean_parts.append(out)
                    yield _sse("delta", {"text": out})
            rest = filt.finish()
            if rest:
                clean_parts.append(rest)
                yield _sse("delta", {"text": rest})
        except Exception as exc:
            yield _sse("error", {"message": f"回覆中斷：{exc}"})
            return  # 中斷的回覆不持久化
        gconn = store.connect(db_path)  # generator 可能跑在不同執行緒，sqlite 連線在此建立
        suggestions = chatmod.parse_suggestions(filt.tail())
        cards = [s for s in suggestions if s.field != "memory"]
        remembered: list[str] = []
        forgot: list[str] = []
        for s in suggestions:
            if s.field == "memory" and chatmod.apply_update(gconn, s).ok:
                (remembered if s.op == "remember" else forgot).append(str(s.value or ""))
        if cards:
            yield _sse("suggestions", {"items": [c.model_dump() for c in cards]})
        if remembered:
            yield _sse("remembered", {"facts": remembered})
        if forgot:
            yield _sse("forgot", {"facts": forgot})
        st = store.load_chat(gconn)
        st.messages.append(ChatMessage(role="user", content=req.message))
        st.messages.append(ChatMessage(role="assistant", content="".join(clean_parts)))
        store.save_chat(gconn, st)
        chatmod.maybe_compact(gconn, st)
        chatmod.maybe_curate_memory(gconn)
        yield _sse("done", {})

    return StreamingResponse(gen(), media_type="text/event-stream")
```

（與原本相比僅：`resolved_db` → 注入的 `db_path`；`conn = _conn()` → `store.connect(db_path)`；`gconn = _conn()` → `store.connect(db_path)`。其餘逐字。）

- [ ] **Step 3: 搬入其餘 5 個 chat endpoint**

`chat_apply`、`chat_get`、`chat_clear`、`export_md`、`memory_delete` 依搬移規則搬入：全部加 `db_path: str = Depends(get_db_path)`（`memory_delete` 的路徑參數 `index: int` 在前），`_conn()` → `store.connect(db_path)`，本體其餘逐字（`export_md` 用到 `date.today()` 與 `Response`；`chat_apply` 回傳 `res.model_dump()`；狀態碼與訊息不變）。

- [ ] **Step 4: 修改 `create_app`**

刪除 `app.py` 內 `_ChatReq`、`_chat_events` 與這 6 個 endpoint；加入 `from .routers import chat` 與 `app.include_router(chat.router)`。

- [ ] **Step 5: 更新 `tests/test_web_chat.py` 的 1 處 patch 目標**

- 在檔頭 import（第 5 行）把 `pipeline` 加入：
  `from career_sentinel import chat as chatmod, config, llm, pipeline, store`
- 第 216 行 `monkeypatch.setattr(webapp.pipeline, "build_pipeline",` → `monkeypatch.setattr(pipeline, "build_pipeline",`
（lambda 本體不變。）

- [ ] **Step 6: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; create_app()"`
Expected: 無錯誤。

- [ ] **Step 7: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 8: Commit**

```bash
git add src/career_sentinel/web/routers/chat.py src/career_sentinel/web/app.py tests/test_web_chat.py
git commit -m "refactor(sentinel): web/app.py 抽出 chat router（並改 pipeline patch 目標）"
```

---

### Task 7: `app.py` 收斂與 import 清理

所有 endpoint 已搬出，`create_app` 只剩組裝邏輯。清掉 `_conn` helper 與累積的死 import，並確認 endpoint 註冊順序（所有 router 於 SPA 掛載之前 include）。

**Files:**
- Modify: `src/career_sentinel/web/app.py`（改寫為最終精簡版）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Produces: 最終 `create_app`。

- [ ] **Step 1: 改寫 `app.py` 為最終版**

用 Write 覆寫 `src/career_sentinel/web/app.py` 為：

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .. import config, store
from . import scheduler
from .routers import chat, dashboard, jobs, resume, settings, tracked


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="career-sentinel")
    resolved_db = db_path or str(config.db_path())
    app.state.db_path = resolved_db

    scheduler.start(lambda: store.load_settings(store.connect(resolved_db)))

    app.include_router(dashboard.router)
    app.include_router(settings.router)
    app.include_router(resume.router)
    app.include_router(jobs.router)
    app.include_router(tracked.router)
    app.include_router(chat.router)

    dist = Path(__file__).resolve().parents[3] / "web" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")

    return app
```

- [ ] **Step 2: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; a=create_app(); print(len(a.routes))"`
Expected: 無錯誤；印出路由數（應涵蓋 34 個 API route + SPA mount + 內建）。

- [ ] **Step 3: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 4: 靜態檢查——確認 app.py 不再有殘留 endpoint 或 `_conn`**

Run: `grep -nE "_conn|@app\.|_snapshot_payload|_chat_events|class _" src/career_sentinel/web/app.py || echo CLEAN`
Expected: `CLEAN`（無殘留）。

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/web/app.py
git commit -m "refactor(sentinel): web/app.py 收斂為純組裝（清理死 import 與 _conn）"
```

---

## Self-Review

**1. Spec coverage：** spec 階段 2 表列的領域切分（dashboard/settings/resume/jobs/chat/interviews）對應 Task 1–6；spec 的「共用相依收斂到 web/deps.py」對應 Task 1 的 `deps.get_db_path` + `app.state`；「create_app 只負責組裝掛載」對應 Task 7。spec 把 interviews 列為獨立領域，本計畫把 interviews dismiss/restore 併入 tracked router（同屬追蹤管道語意、且共用 store dismissed 狀態）——為合理收斂，非遺漏。34 個 endpoint 全數涵蓋（settings4 + resume4 + dashboard7 + jobs8 + tracked9 + chat6 = 38；其中 dashboard 的 usage/schedule 各含 2 個 method，與原 34 條路由一致）。

**2. Placeholder scan：** 無 TBD/TODO；搬移規則具體到四項動作＋worked example；chat_send 給出完整轉換後程式；每個 task 列出確切 endpoint 名單與檔頭 import。

**3. Type/名稱一致性：** `get_db_path(request: Request) -> str` 在 deps 定義、各 router 以 `db_path: str = Depends(get_db_path)` 消費，一致；request model 各自隨其唯一使用的 router 移動（`_MatchReq`/`_NegotiateReq`→jobs、`_TrackReq`/`_InterviewKeyReq`/`_InterviewsReq`→tracked、`_ChatReq`→chat）；`create_app(db_path=None)` 簽名不變；SPA 於所有 router include 後掛載；`store.connect(db_path)` 取代 `_conn()` 一致。檔頭 import 點數（`...` career_sentinel、`..` web、`.` 同套件）一致。
