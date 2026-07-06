# SP20：offer 比較 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在卡片 Drawer 提供「標記錄取（填 offer 明細）／標記未錄取／重設」入口，並在求職中心用並排比較表呈現所有 offer、高亮最高年薪。

**Architecture:** 新增 `OfferDetail` 模型，序列化存進 `TrackedJob.offer_json`（比照 match_json/tailor_json 冪等 migration）。手動終端狀態走新的 `store.set_tracked_state`（強制設定，繞過 `merge_tracked_job` 的 rank 防降級），與訊號自動路徑並存。`build_pipeline` 把 offer_json 解析成 `PipelineJob.offer` 帶給前端；Drawer 加狀態區，Dashboard 加 offer 並排比較表＋未錄取收合群組。

**Tech Stack:** Python 3.12 / Pydantic v2 / FastAPI / SQLite；React 18 + Vite + Mantine 7 + TanStack Query。

## Global Constraints

- **兩條寫入路徑並存、語意分明**：`merge_tracked_job`（訊號帶動、防降級，維持 SP15/SP17 行為，**不改**）與 `set_tracked_state`（使用者手動、強制設定/清除終端）。比對/客製化追蹤仍走 `merge_tracked_job`。
- **offer_json 生命週期**：只有 `state == "offer"` 才有 offer_json；設 rejected / reset 一律清空，杜絕殘留舊 offer 顯示在比較表。
- **相容加法式**：`TrackedJob` 加 `offer_json`、`PipelineJob` 加 `offer` 皆加法；`offer_json` 靠 `_migrate` 冪等 ALTER（不丟資料）；Pydantic v2 忽略多餘 key。既有回傳只增不減（`GET /api/tracked/{code}` 多回 `offer`）。
- **build_pipeline 韌性不變**：整體 try/except → []；offer 解析再加 per-job try，壞資料不整批消失。
- **最高年薪高亮純前端、純顯示**：不寫回、不改明細；折算月薪×12 只用於比大小。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 `127.0.0.1`。
- **測試指令（後端）**：於 `sentinel/` 目錄用專案 venv：`./.venv/Scripts/python.exe -m pytest -q`（預設 shell python 是錯的 venv，缺 pytest）。
- **測試指令（前端）**：於 `sentinel/web/frontend/` 用 `npm run build`（= `tsc -b && vite build`）；刪除/新增後清乾淨殘留 import。

---

## File Structure

- `sentinel/src/career_sentinel/models.py` — 加 `OfferDetail`、`TrackedJob.offer_json`、`PipelineJob.offer`。
- `sentinel/src/career_sentinel/store.py` — schema 加 offer_json 欄、`_migrate` 補欄、三個讀寫函式補欄、新增 `set_tracked_state`。
- `sentinel/src/career_sentinel/pipeline.py` — 加 `_parse_offer` 並在合併時帶出 `pj.offer`。
- `sentinel/src/career_sentinel/web/app.py` — import `OfferDetail`；三個端點；`GET /api/tracked/{code}` 加 `offer`。
- `sentinel/web/frontend/src/api.ts` — `OfferDetail` 型別、`PipelineJob.offer`、`TrackedCard.offer`、`setOffer`/`rejectJob`/`resetTracked`。
- `sentinel/web/frontend/src/JobCardDrawer.tsx` — 狀態區（標記錄取表單／未錄取／重設）。
- `sentinel/web/frontend/src/Dashboard.tsx` — offer 並排比較表＋未錄取收合群組。
- 測試：`sentinel/tests/test_tracked_jobs_store.py`、`sentinel/tests/test_pipeline.py`、`sentinel/tests/test_web_tracked.py`。

---

### Task 1: 資料模型 ＋ store 欄位（offer_json 持久化）

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`
- Modify: `sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_tracked_jobs_store.py`

**Interfaces:**
- Produces:
  - `OfferDetail(BaseModel)`：`salary_year: int|None`、`salary_month: int|None`、`location: str`、`level: str`、`start_date: str`、`notes: str`（皆有預設）。
  - `TrackedJob.offer_json: str = ""`（序列化的 OfferDetail；空＝無明細）。
  - `PipelineJob.offer: OfferDetail | None = None`（本任務僅定義欄位，Task 2 才填值）。
  - `store.load_tracked_jobs`/`get_tracked_job`/`upsert_tracked_job` 讀寫 `offer_json`。

- [ ] **Step 1: 寫失敗測試（offer_json round-trip ＋ 舊 DB 遷移）**

在 `sentinel/tests/test_tracked_jobs_store.py` 末尾加：

```python
def test_offer_json_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(
        code="of1", state="offer", offer_json='{"salary_year": 1200000, "location": "台北"}'))
    got = store.get_tracked_job(conn, "of1")
    assert got is not None
    assert got.offer_json == '{"salary_year": 1200000, "location": "台北"}'


def test_offer_json_defaults_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="of2", state="matched"))
    assert store.get_tracked_job(conn, "of2").offer_json == ""


def test_migrate_adds_offer_json_to_existing_table(tmp_path):
    # 模擬「offer_json 進 schema 之前」的舊 DB：完整欄位但缺 offer_json
    import sqlite3
    p = tmp_path / "db.sqlite"
    raw = sqlite3.connect(str(p))
    raw.execute(
        "CREATE TABLE tracked_jobs ("
        "code TEXT PRIMARY KEY, company TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', "
        "url TEXT NOT NULL DEFAULT '', salary TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'interested', "
        "match_score INTEGER, created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '', "
        "match_json TEXT NOT NULL DEFAULT '', tailor_json TEXT NOT NULL DEFAULT '')"
    )
    raw.execute("INSERT INTO tracked_jobs (code, state) VALUES ('old1', 'matched')")
    raw.commit()
    raw.close()
    conn = store.connect(p)  # 應冪等補上 offer_json 欄，不丟資料
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tracked_jobs)")}
    assert "offer_json" in cols
    got = store.get_tracked_job(conn, "old1")
    assert got is not None and got.state == "matched" and got.offer_json == ""
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: FAIL（`TrackedJob` 無 `offer_json` 欄 → `TypeError`/`ValidationError`；或 SELECT 找不到 offer_json 欄）

- [ ] **Step 3: 加 `OfferDetail` 與模型欄位（`models.py`）**

在 `class JobPreferences` 之後、`class TrackedJob` 之前插入：

```python
class OfferDetail(BaseModel):
    salary_year: int | None = None   # 年薪
    salary_month: int | None = None  # 月薪
    location: str = ""
    level: str = ""                  # 職級
    start_date: str = ""             # 到職日
    notes: str = ""
```

`class TrackedJob` 的 `tailor_json: str = ""` 後加一行：

```python
    offer_json: str = ""
```

`class PipelineJob` 的 `match_score: int | None = None` 後加一行：

```python
    offer: "OfferDetail | None" = None
```

（`OfferDetail` 定義在 `PipelineJob` 之前，字串前置引用非必須，但為清楚用引號無妨。）

- [ ] **Step 4: store schema ＋ migrate ＋ 讀寫欄位（`store.py`）**

`_SCHEMA` 的 `tracked_jobs` 區塊，把 `tailor_json` 行改為含逗號並加 offer_json 行：

```python
    match_json TEXT NOT NULL DEFAULT '',
    tailor_json TEXT NOT NULL DEFAULT '',
    offer_json TEXT NOT NULL DEFAULT ''
);
```

`_migrate` 欄位迴圈補 `offer_json`：

```python
def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tracked_jobs)")}
    for col in ("match_json", "tailor_json", "offer_json"):
        if col not in cols:
            conn.execute(f"ALTER TABLE tracked_jobs ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    conn.commit()
```

`load_tracked_jobs` 改為（SELECT 末尾加 offer_json、解構加 oj、TrackedJob 加 offer_json）：

```python
def load_tracked_jobs(conn: sqlite3.Connection) -> list[TrackedJob]:
    rows = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json FROM tracked_jobs ORDER BY updated_at DESC"
    )
    return [
        TrackedJob(
            code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
            match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
            tailor_json=tj or "", offer_json=oj or "",
        )
        for c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj in rows
    ]
```

`get_tracked_job` 同樣改：

```python
def get_tracked_job(conn: sqlite3.Connection, code: str) -> TrackedJob | None:
    row = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json FROM tracked_jobs WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        return None
    c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj = row
    return TrackedJob(
        code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
        match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
        tailor_json=tj or "", offer_json=oj or "",
    )
```

`upsert_tracked_job` 改為 12 欄：

```python
def upsert_tracked_job(conn: sqlite3.Connection, job: TrackedJob) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_jobs "
        "(code, company, title, url, salary, state, match_score, created_at, updated_at, match_json, tailor_json, offer_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (job.code, job.company, job.title, job.url, job.salary, job.state,
         job.match_score, job.created_at, job.updated_at, job.match_json, job.tailor_json, job.offer_json),
    )
    conn.commit()
```

- [ ] **Step 5: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: PASS（含既有測試）

- [ ] **Step 6: 跑全套回歸（模型/pipeline/web 皆碰 TrackedJob）**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠；既有 merge_tracked_job/pipeline/web tracked 測試不受影響）

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_tracked_jobs_store.py
git commit -m "feat(sentinel): OfferDetail 模型 + tracked_jobs.offer_json 持久化（SP20）"
```

---

### Task 2: 手動終端狀態（set_tracked_state）＋ pipeline 帶出 offer

**Files:**
- Modify: `sentinel/src/career_sentinel/store.py`
- Modify: `sentinel/src/career_sentinel/pipeline.py`
- Test: `sentinel/tests/test_tracked_jobs_store.py`、`sentinel/tests/test_pipeline.py`

**Interfaces:**
- Consumes: Task 1 的 `OfferDetail`、`TrackedJob.offer_json`、`PipelineJob.offer`、`store.get_tracked_job`/`upsert_tracked_job`。
- Produces:
  - `store.set_tracked_state(conn, code, state, *, offer: OfferDetail | None = None) -> str`：強制設定狀態，`state=="offer"` 且 `offer` 非 None 時序列化存 offer_json，其餘一律清空；保留 created_at 與其他欄位；不存在則新建；回最終 state。
  - `pipeline.build_pipeline` 對 offer-state（offer_json 非空）job 於 `PipelineJob.offer` 帶出明細。

- [ ] **Step 1: 寫失敗測試（set_tracked_state）**

在 `sentinel/tests/test_tracked_jobs_store.py` 頂部 import 補 `OfferDetail`：

```python
from career_sentinel.models import OfferDetail, TrackedJob
```

末尾加：

```python
def test_set_offer_stores_detail(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    of = OfferDetail(salary_year=1200000, salary_month=90000, location="台北",
                     level="資深", start_date="2026-09-01", notes="含年終")
    final = store.set_tracked_state(conn, "of1", "offer", offer=of)
    assert final == "offer"
    got = store.get_tracked_job(conn, "of1")
    assert got.state == "offer"
    parsed = OfferDetail.model_validate_json(got.offer_json)
    assert parsed.salary_year == 1200000 and parsed.location == "台北" and parsed.level == "資深"


def test_set_reject_clears_offer(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=100))
    store.set_tracked_state(conn, "of1", "rejected")
    got = store.get_tracked_job(conn, "of1")
    assert got.state == "rejected" and got.offer_json == ""


def test_reset_from_offer_clears(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=100))
    store.set_tracked_state(conn, "of1", "interested")
    got = store.get_tracked_job(conn, "of1")
    assert got.state == "interested" and got.offer_json == ""


def test_set_state_new_code_creates(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "new1", "offer", offer=OfferDetail(salary_month=60000))
    assert store.get_tracked_job(conn, "new1").state == "offer"


def test_set_state_keeps_created_at(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="k1", state="interviewing", created_at="2026-07-01T00:00:00"))
    store.set_tracked_state(conn, "k1", "offer", offer=OfferDetail(salary_year=1))
    got = store.get_tracked_job(conn, "k1")
    assert got.created_at == "2026-07-01T00:00:00" and got.state == "offer"
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: FAIL（`store.set_tracked_state` 不存在 → `AttributeError`）

- [ ] **Step 3: 加 `set_tracked_state`（`store.py`）**

`store.py` 頂部 models import 清單加 `OfferDetail`：

```python
from .models import (
    Application, ChatState, CompanyResearch, DismissedInterviews, Interview, JobPreferences,
    MemoryState, Message, OfferDetail, ResumeState, Settings, Snapshot, TrackedJob, Viewer,
)
```

在 `merge_tracked_job` 之後加：

```python
def set_tracked_state(
    conn: sqlite3.Connection, code: str, state: str, *, offer: OfferDetail | None = None,
) -> str:
    """強制設定追蹤職缺狀態（使用者手動；繞過 merge 的 rank 防降級）。
    state=="offer" 且 offer 非 None 時序列化存 offer_json；其餘一律清空 offer_json。
    保留既有 created_at 與其他欄位；不存在則新建。回最終 state。"""
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_tracked_job(conn, code)
    offer_json = (
        json.dumps(offer.model_dump(), ensure_ascii=False)
        if (state == "offer" and offer is not None) else ""
    )
    if existing is not None:
        upsert_tracked_job(conn, TrackedJob(
            code=code, company=existing.company, title=existing.title, url=existing.url,
            salary=existing.salary, state=state, match_score=existing.match_score,
            created_at=existing.created_at or now, updated_at=now,
            match_json=existing.match_json, tailor_json=existing.tailor_json, offer_json=offer_json,
        ))
    else:
        upsert_tracked_job(conn, TrackedJob(
            code=code, state=state, created_at=now, updated_at=now, offer_json=offer_json,
        ))
    return state
```

- [ ] **Step 4: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: PASS

- [ ] **Step 5: 寫失敗測試（pipeline 帶出 offer）**

在 `sentinel/tests/test_pipeline.py` 頂部 import 補 `OfferDetail`：

```python
from career_sentinel.models import (
    Application, Interview, OfferDetail, Snapshot, TrackedJob,
)
```

末尾加：

```python
def test_build_offer_carries_detail(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "of9", "offer",
                            offer=OfferDetail(salary_year=1200000, location="台北", level="資深"))
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].state == "offer"
    assert jobs[0].offer is not None
    assert jobs[0].offer.salary_year == 1200000 and jobs[0].offer.location == "台北"


def test_build_non_offer_has_no_offer(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="m1", state="matched", match_score=70))
    jobs = pipeline.build_pipeline(conn)
    assert jobs[0].offer is None


def test_build_bad_offer_json_survives(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="b1", state="offer", offer_json="{not json"))
    jobs = pipeline.build_pipeline(conn)
    assert jobs[0].offer is None and jobs[0].state == "offer"


def test_build_reset_returns_to_signal_state(tmp_path):
    snap = Snapshot(interviews=[
        Interview(company="戊", job_title="後端", when="2026-07-13 10:00:00",
                  location="台北", job_url="https://www.104.com.tw/job/ff4gg"),
    ])
    conn = _conn_with(tmp_path, snap)
    store.set_tracked_state(conn, "ff4gg", "offer", offer=OfferDetail(salary_year=1))
    assert pipeline.build_pipeline(conn)[0].state == "offer"
    store.set_tracked_state(conn, "ff4gg", "interested")  # reset
    j = pipeline.build_pipeline(conn)[0]
    assert j.state == "interviewing" and j.offer is None  # 回歸 104 訊號
```

- [ ] **Step 6: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -q`
Expected: FAIL（`PipelineJob.offer` 恆為 None → `test_build_offer_carries_detail` 失敗）

- [ ] **Step 7: pipeline 解析 offer（`pipeline.py`）**

import 補 `OfferDetail`：

```python
from .models import OfferDetail, PipelineJob, Snapshot, interview_key
```

在 `_build` 函式之前（或 `effective_state` 之後）加 helper：

```python
def _parse_offer(offer_json: str) -> OfferDetail | None:
    if not offer_json:
        return None
    try:
        return OfferDetail.model_validate_json(offer_json)
    except Exception:
        return None
```

`_build` 的 tracked 併入迴圈，在 `if tj is not None:` 區塊尾端加一行：

```python
        if tj is not None:
            pj.url = tj.url or pj.url
            pj.salary = tj.salary or pj.salary
            if tj.match_score is not None:
                pj.match_score = tj.match_score
            pj.company = pj.company or tj.company
            pj.title = pj.title or tj.title
            pj.offer = _parse_offer(tj.offer_json)
        pj.state = effective_state(tj.state if tj else None, signal.get(key, 0))
```

純手動新增迴圈，在 `pj.state = effective_state(tj.state, 0)` 後加一行：

```python
        pj.state = effective_state(tj.state, 0)
        pj.offer = _parse_offer(tj.offer_json)
        jobs[code] = pj
```

- [ ] **Step 8: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_pipeline.py tests/test_tracked_jobs_store.py -q`
Expected: PASS

- [ ] **Step 9: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 10: Commit**

```bash
git add sentinel/src/career_sentinel/store.py sentinel/src/career_sentinel/pipeline.py sentinel/tests/test_tracked_jobs_store.py sentinel/tests/test_pipeline.py
git commit -m "feat(sentinel): set_tracked_state 強制設定終端 + pipeline 帶出 offer 明細（SP20）"
```

---

### Task 3: web 端點（offer / reject / reset）＋ GET 回 offer

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_tracked.py`

**Interfaces:**
- Consumes: Task 2 的 `store.set_tracked_state`；Task 1 的 `OfferDetail`、`TrackedJob.offer_json`。
- Produces:
  - `POST /api/tracked/{code}/offer`（body: `OfferDetail`）→ `{status, state}`，state=="offer"。
  - `POST /api/tracked/{code}/reject` → `{status, state}`，state=="rejected"。
  - `POST /api/tracked/{code}/reset` → `{status, state}`，state=="interested"。
  - `GET /api/tracked/{code}` 回傳新增 `offer`（offer-state 才有明細，否則 None）。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_web_tracked.py` 末尾加：

```python
def test_set_offer_endpoint(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked/of1/offer", json={
        "salary_year": 1200000, "salary_month": 90000, "location": "台北",
        "level": "資深", "start_date": "2026-09-01", "notes": "含年終"})
    assert r.status_code == 200 and r.json()["state"] == "offer"
    got = c.get("/api/tracked/of1").json()
    assert got["state"] == "offer"
    assert got["offer"]["salary_year"] == 1200000 and got["offer"]["location"] == "台北"


def test_reject_endpoint_clears_offer(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked/of1/offer", json={"salary_year": 100})
    r = c.post("/api/tracked/of1/reject")
    assert r.json()["state"] == "rejected"
    got = c.get("/api/tracked/of1").json()
    assert got["state"] == "rejected" and got["offer"] is None


def test_reset_endpoint_clears_offer(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked/of1/offer", json={"salary_year": 100})
    r = c.post("/api/tracked/of1/reset")
    assert r.json()["state"] == "interested"
    got = c.get("/api/tracked/of1").json()
    assert got["state"] == "interested" and got["offer"] is None


def test_tracked_get_non_offer_offer_none(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "m1", "match_score": 70})
    got = c.get("/api/tracked/m1").json()
    assert got["offer"] is None
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_tracked.py -q`
Expected: FAIL（端點 404；`GET` 回傳無 `offer` key → `KeyError`）

- [ ] **Step 3: import `OfferDetail`（`app.py`）**

把 `from ..models import ...` 那行加入 `OfferDetail`：

```python
from ..models import ChatMessage, ChatState, JobPreferences, OfferDetail, ResumeState, Settings, SuggestedUpdate, TrackedJob, interview_key
```

- [ ] **Step 4: 加三個端點（`app.py`）**

在 `DELETE /api/tracked/{code}`（`untrack_job`）之後加：

```python
    @app.post("/api/tracked/{code}/offer")
    def tracked_set_offer(code: str, offer: OfferDetail) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        final = store.set_tracked_state(_conn(), code, "offer", offer=offer)
        return {"status": "ok", "state": final}

    @app.post("/api/tracked/{code}/reject")
    def tracked_set_reject(code: str) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        final = store.set_tracked_state(_conn(), code, "rejected")
        return {"status": "ok", "state": final}

    @app.post("/api/tracked/{code}/reset")
    def tracked_reset(code: str) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        final = store.set_tracked_state(_conn(), code, "interested")
        return {"status": "ok", "state": final}
```

- [ ] **Step 5: `GET /api/tracked/{code}` 加 offer（`app.py`）**

`tracked_get` 的兩個 return 各加 `offer`：

```python
    @app.get("/api/tracked/{code}")
    def tracked_get(code: str) -> dict:
        tj = store.get_tracked_job(_conn(), code)
        if tj is None:
            return {"code": code, "found": False, "state": "", "match_score": None,
                    "match": None, "tailor": None, "offer": None}
        return {
            "code": tj.code, "found": True, "state": tj.state, "match_score": tj.match_score,
            "match": json.loads(tj.match_json) if tj.match_json else None,
            "tailor": json.loads(tj.tailor_json) if tj.tailor_json else None,
            "offer": json.loads(tj.offer_json) if tj.offer_json else None,
        }
```

- [ ] **Step 6: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_tracked.py -q`
Expected: PASS

- [ ] **Step 7: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_tracked.py
git commit -m "feat(sentinel): /api/tracked offer/reject/reset 端點 + GET 回 offer（SP20）"
```

---

### Task 4: 前端 api.ts ＋ 卡片 Drawer 狀態區

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`
- Modify: `sentinel/web/frontend/src/JobCardDrawer.tsx`

**Interfaces:**
- Consumes: Task 3 的三個端點與 `GET /api/tracked/{code}` 的 `offer`。
- Produces: `OfferDetail` 型別、`setOffer`/`rejectJob`/`resetTracked`；Drawer 狀態區。

- [ ] **Step 1: api.ts 加型別與函式**

`PipelineJob` interface 的 `watched: boolean;` 後加：

```ts
  offer?: OfferDetail | null;
```

在 `TrackReq` interface 之前加 `OfferDetail` 型別：

```ts
export interface OfferDetail {
  salary_year: number | null;
  salary_month: number | null;
  location: string;
  level: string;
  start_date: string;
  notes: string;
}
```

`TrackedCard` interface 的 `tailor: TailoredApplication | null;` 後加：

```ts
  offer: OfferDetail | null;
```

在 `untrackJob` 之後加三個函式：

```ts
export async function setOffer(code: string, offer: OfferDetail): Promise<Response> {
  return fetch(`/api/tracked/${encodeURIComponent(code)}/offer`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(offer),
  });
}

export async function rejectJob(code: string): Promise<Response> {
  return fetch(`/api/tracked/${encodeURIComponent(code)}/reject`, { method: "POST" });
}

export async function resetTracked(code: string): Promise<Response> {
  return fetch(`/api/tracked/${encodeURIComponent(code)}/reset`, { method: "POST" });
}
```

- [ ] **Step 2: Drawer 狀態區（`JobCardDrawer.tsx`）**

import 補（Mantine 元件與 api）：

```tsx
import {
  ActionIcon, Anchor, Button, Drawer, Group, List, NumberInput, Paper, Progress, Stack,
  Text, Textarea, TextInput, ThemeIcon,
} from "@mantine/core";
```

```tsx
import {
  getResume, getTrackedJob, matchJob, openApplyPage, rejectJob, resetTracked, setOffer,
  tailorApplication, trackJob, type MatchResult, type OfferDetail, type TailoredApplication,
} from "./api";
```

在既有 state 宣告區（`const [copied, setCopied] = useState(false);` 後）加狀態區 state：

```tsx
  const [state, setState] = useState<string>("");
  const [offer, setOfferState] = useState<OfferDetail | null>(null);
  const [editingOffer, setEditingOffer] = useState(false);
  const [form, setForm] = useState<OfferDetail>({
    salary_year: null, salary_month: null, location: "", level: "", start_date: "", notes: "",
  });
  const [stateBusy, setStateBusy] = useState(false);
```

在既有「開啟時載入快取」的 `useEffect` 裡，補讀 state/offer（把 setter 加進 then）：

```tsx
  useEffect(() => {
    if (!opened || !job) return;
    setErr(null); setMatch(null); setTailor(null);
    setState(""); setOfferState(null); setEditingOffer(false);
    getTrackedJob(job.code).then((r) => r.json()).then((c) => {
      if (c.match) setMatch(c.match);
      if (c.tailor) setTailor(c.tailor);
      setState(c.state || "");
      if (c.offer) {
        setOfferState(c.offer);
        setForm(c.offer);
      }
    }).catch(() => {});
  }, [opened, job?.code]);
```

在 `runMatch`/`runTailor` 等函式旁加狀態操作函式：

```tsx
  async function saveOffer() {
    if (!job) return;
    setErr(null); setStateBusy(true);
    try {
      const r = await setOffer(job.code, form);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "儲存失敗"); return; }
      setState("offer"); setOfferState(form); setEditingOffer(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setStateBusy(false); }
  }

  async function markReject() {
    if (!job) return;
    setErr(null); setStateBusy(true);
    try {
      const r = await rejectJob(job.code);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "操作失敗"); return; }
      setState("rejected"); setOfferState(null); setEditingOffer(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setStateBusy(false); }
  }

  async function resetState() {
    if (!job) return;
    setErr(null); setStateBusy(true);
    try {
      const r = await resetTracked(job.code);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "操作失敗"); return; }
      setState("interested"); setOfferState(null); setEditingOffer(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setStateBusy(false); }
  }
```

在 `<Stack gap="lg">` 內、`{err && ...}` 之後、比對 Paper 之前插入狀態區：

```tsx
          {/* 狀態 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} mb="sm">狀態</Text>
            {state === "offer" && !editingOffer ? (
              <Stack gap={6}>
                <Text c="teal.5" size="sm" fw={600}>已錄取</Text>
                {offer && (
                  <Text size="xs" c="dimmed">
                    {offer.salary_year != null ? `年薪 ${offer.salary_year}` : ""}
                    {offer.salary_month != null ? ` · 月薪 ${offer.salary_month}` : ""}
                    {offer.location ? ` · ${offer.location}` : ""}
                    {offer.level ? ` · ${offer.level}` : ""}
                    {offer.start_date ? ` · ${offer.start_date}` : ""}
                  </Text>
                )}
                {offer?.notes && <Text size="xs" c="dimmed">{offer.notes}</Text>}
                <Group gap="sm" mt={4}>
                  <Button size="compact-sm" variant="light" onClick={() => setEditingOffer(true)}>編輯</Button>
                  <Button size="compact-sm" variant="subtle" color="gray" onClick={resetState} loading={stateBusy}>重設</Button>
                </Group>
              </Stack>
            ) : state === "rejected" ? (
              <Group justify="space-between">
                <Text c="dimmed" size="sm">已標記未錄取</Text>
                <Button size="compact-sm" variant="subtle" color="gray" onClick={resetState} loading={stateBusy}>重設</Button>
              </Group>
            ) : editingOffer ? (
              <Stack gap="sm">
                <Group grow>
                  <NumberInput label="年薪" value={form.salary_year ?? undefined} thousandSeparator=","
                    onChange={(v) => setForm({ ...form, salary_year: typeof v === "number" ? v : null })} />
                  <NumberInput label="月薪" value={form.salary_month ?? undefined} thousandSeparator=","
                    onChange={(v) => setForm({ ...form, salary_month: typeof v === "number" ? v : null })} />
                </Group>
                <Group grow>
                  <TextInput label="地點" value={form.location}
                    onChange={(e) => setForm({ ...form, location: e.currentTarget.value })} />
                  <TextInput label="職級" value={form.level}
                    onChange={(e) => setForm({ ...form, level: e.currentTarget.value })} />
                </Group>
                <TextInput label="到職日" value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.currentTarget.value })} />
                <Textarea label="備註" autosize minRows={2} value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })} />
                <Group gap="sm">
                  <Button size="compact-sm" onClick={saveOffer} loading={stateBusy}>儲存</Button>
                  <Button size="compact-sm" variant="subtle" color="gray" onClick={() => setEditingOffer(false)}>取消</Button>
                </Group>
              </Stack>
            ) : (
              <Group gap="sm">
                <Button size="compact-sm" variant="light" color="teal" onClick={() => setEditingOffer(true)}>標記錄取</Button>
                <Button size="compact-sm" variant="light" color="gray" onClick={markReject} loading={stateBusy}>標記未錄取</Button>
              </Group>
            )}
          </Paper>
```

- [ ] **Step 3: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（`tsc -b && vite build` 無型別/未用 import 錯誤）

- [ ] **Step 4: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/JobCardDrawer.tsx
git commit -m "feat(sentinel): 卡片 Drawer offer/未錄取/重設 狀態區 + api（SP20）"
```

---

### Task 5: Dashboard offer 並排比較表 ＋ 未錄取群組

**Files:**
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`

**Interfaces:**
- Consumes: Task 2 的 `PipelineJob.offer`；Task 4 的 `resetTracked`。

- [ ] **Step 1: import 補 Table 與 resetTracked**

`@mantine/core` import 加 `Table`：

```tsx
import { ActionIcon, Anchor, Badge, Button, Grid, Group, Paper, Table, Text, Title } from "@mantine/core";
```

`./api` import 加 `resetTracked`：

```tsx
import { type PipelineJob, dismissInterview, getSnapshot, getStatus, resetTracked, restoreInterview, untrackJob } from "./api";
```

- [ ] **Step 2: 分群與最高年薪計算**

在既有分群（`const tailoredJobs = ...` 後）加：

```tsx
  const offerJobs = pipe.filter((j) => j.state === "offer");
  const rejectedJobs = pipe.filter((j) => j.state === "rejected");

  // 折算年薪（月薪×12 只用於比大小；純顯示不改資料）
  const annualized = (j: PipelineJob) =>
    j.offer?.salary_year ?? (j.offer?.salary_month != null ? j.offer.salary_month * 12 : null);
  const bestAnnual = Math.max(-1, ...offerJobs.map((j) => annualized(j) ?? -1));
```

在 `const [showDone, setShowDone] = useState(false);` 後加未錄取收合 state：

```tsx
  const [showRejected, setShowRejected] = useState(false);
```

加重設處理函式（在 `untrack` 附近）：

```tsx
  const resetJob = (code: string) => async () => {
    try {
      await resetTracked(code);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { window.alert("網路錯誤，請重試"); }
  };
```

- [ ] **Step 3: 管道渲染條件加入 offer/rejected**

把 `Dashboard.tsx` 第 156 行附近的管道區塊存在判斷擴充（加 offerJobs/rejectedJobs）：

```tsx
      {s && (offerJobs.length > 0 || upcomingJobs.length > 0 || appliedJobs.length > 0 || doneJobs.length > 0 || tailoredSorted.length > 0 || matchedSorted.length > 0 || interestedJobs.length > 0 || rejectedJobs.length > 0) && (
```

- [ ] **Step 4: offer 比較表（放在 `<SectionTitle id="sec-pipeline">職缺管道</SectionTitle>` 之後、面試中群組之前）**

```tsx
          {offerJobs.length > 0 && (
            <>
              <Text size="xs" c="teal.5" mb={6} mt="xs" fw={600} style={{ letterSpacing: 1 }}>offer 比較</Text>
              <Table striped highlightOnHover withTableBorder verticalSpacing="sm" mb="md">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>公司 · 職稱</Table.Th>
                    <Table.Th>年薪</Table.Th>
                    <Table.Th>月薪</Table.Th>
                    <Table.Th>地點</Table.Th>
                    <Table.Th>職級</Table.Th>
                    <Table.Th>到職日</Table.Th>
                    <Table.Th>分數</Table.Th>
                    <Table.Th>備註</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {offerJobs.map((j: PipelineJob) => {
                    const best = bestAnnual > 0 && (annualized(j) ?? -1) === bestAnnual;
                    return (
                      <Table.Tr key={j.key} style={{ cursor: "pointer" }} onClick={openCard(j)}>
                        <Table.Td>
                          <Text size="sm" fw={600}>{j.company}</Text>
                          <Text size="xs" c="dimmed">{j.title}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm" c={best ? "teal.5" : undefined} fw={best ? 700 : undefined}>
                            {j.offer?.salary_year != null ? j.offer.salary_year.toLocaleString() : "—"}
                          </Text>
                        </Table.Td>
                        <Table.Td><Text size="sm">{j.offer?.salary_month != null ? j.offer.salary_month.toLocaleString() : "—"}</Text></Table.Td>
                        <Table.Td><Text size="sm">{j.offer?.location || "—"}</Text></Table.Td>
                        <Table.Td><Text size="sm">{j.offer?.level || "—"}</Text></Table.Td>
                        <Table.Td><Text size="sm">{j.offer?.start_date || "—"}</Text></Table.Td>
                        <Table.Td><Text size="sm">{j.match_score != null ? j.match_score : "—"}</Text></Table.Td>
                        <Table.Td><Text size="xs" c="dimmed" style={{ maxWidth: 180, whiteSpace: "pre-wrap" }}>{j.offer?.notes || "—"}</Text></Table.Td>
                      </Table.Tr>
                    );
                  })}
                </Table.Tbody>
              </Table>
            </>
          )}
```

- [ ] **Step 5: 未錄取收合群組（放在管道區塊末尾、`interestedJobs` 群組之後）**

```tsx
          {rejectedJobs.length > 0 && (
            <>
              <Button variant="subtle" color="gray" size="compact-xs" mt="md" onClick={() => setShowRejected((v) => !v)}>
                {showRejected ? "收合未錄取" : `未錄取 ${rejectedJobs.length} 筆`}
              </Button>
              {showRejected && rejectedJobs.map((j: PipelineJob) => (
                <Row key={j.key}>
                  <Text size="sm" truncate style={{ opacity: 0.55, minWidth: 0, flex: 1 }}>
                    <Text span fw={600}>{j.company}</Text>
                    <Text span c="dimmed"> · {j.title}</Text>
                  </Text>
                  <ActionIcon variant="subtle" color="gray" size="md" title="重設（清除未錄取）" style={{ flexShrink: 0 }}
                    onClick={resetJob(j.code)}>
                    <IconArrowBackUp size={15} />
                  </ActionIcon>
                </Row>
              ))}
            </>
          )}
```

- [ ] **Step 6: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（無型別/未用 import 錯誤；`IconArrowBackUp` 已在既有 import 中）

- [ ] **Step 7: Commit**

```bash
git add sentinel/web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 求職中心 offer 並排比較表 + 未錄取群組（SP20）"
```

---

## Self-Review

**Spec coverage：**
- 資料模型（OfferDetail/offer_json/PipelineJob.offer/migration）→ Task 1 ✅
- set_tracked_state（強制設定、清 offer_json、保留 created_at）→ Task 2 ✅
- build_pipeline 帶出 offer（含 per-job try）→ Task 2 ✅
- 三端點 offer/reject/reset ＋ GET 回 offer → Task 3 ✅
- Drawer 狀態區（標記錄取表單/未錄取/重設/編輯）→ Task 4 ✅
- Dashboard offer 並排比較表（高亮最高年薪，月薪×12 折算）＋ 未錄取收合群組 → Task 5 ✅
- 兩條寫入路徑並存、offer_json 生命週期、韌性、純前端高亮 → Global Constraints，各 Task 遵守 ✅

**Placeholder scan：** 無 TBD/TODO；每個改碼步驟含完整程式碼與確切指令。

**Type consistency：** `OfferDetail` 欄位（salary_year/salary_month/location/level/start_date/notes）於 models.py、api.ts、Drawer、Dashboard 一致；`set_tracked_state(conn, code, state, *, offer=None) -> str` 於 store/pipeline/app/測試一致；`PipelineJob.offer` 於後端與 api.ts 一致；`setOffer/rejectJob/resetTracked` 命名一致。
