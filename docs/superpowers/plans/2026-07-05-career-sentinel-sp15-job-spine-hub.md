# SP15：職缺脊椎 ＋ 求職中心 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓職缺變成持久化、有狀態的物件（新 `tracked_jobs` 表），並用一支純讀合併引擎把 104 scrape 的投遞/面試 ＋ 手動追蹤層併成一份「按狀態分組的職缺管道」，儀表板擴張成求職中心呈現。

**Architecture:** 後端新增 `tracked_jobs` 表（app 端手動層，SP15 尚無寫入者，先鋪好）＋ 新 `pipeline.py` 合併引擎（讀最新 snapshot 的 applications/interviews ＋ tracked_jobs，用 104 job code 併成 `PipelineJob` 清單，算有效狀態）；`/api/snapshot` best-effort 新增 `pipeline` 欄位；前端 `Dashboard.tsx` 把「我的應徵＋即將面試」重排成按狀態分組的管道（面試中群組完整保留 SP7 功能），誰看過我/訊息移到管道下方當次要訊號區。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、SQLite、pytest；React 18 ＋ Vite ＋ Mantine 7 ＋ TanStack Query。

## Global Constraints

- **不得弄丟 SP7 面試功能**：`面試中` 群組必須保留 gcal 連結（加入 Google 日曆）、知道了/還原（dismiss/restore，含「已處理 N 場」收合）、看職缺、104 對話串。
- **合併引擎純讀、best-effort**：`build_pipeline` 與 payload 注入都用 `try/except` 包住，任何錯誤回空清單/空欄位，**絕不影響 snapshot 讀取或 scrape**。
- **相容**：`/api/snapshot` 既有欄位（`applications`/`interviews`/`viewers`/`messages`/`digest`/`failed_readers`）保留輸出；只**新增** `pipeline`。
- **tracked_jobs 空表要能正常運作**：管道只顯示 104 帶入的 已投遞/面試中，上線即有內容。
- **104 job code 為職缺主鍵**；interview 無 code（`jobfetch.extract_job_code` raise `ValueError`）時以 `interview_key(iv)` 退回鍵，不得因缺 code 而崩。
- KPI 維持現有 4 個（誰看過我／即將面試／新訊息／投遞中），本 SP 不動；沿用現有 Cockpit 主題與 `PageContainer`/`Kpi`/`Row`/`SectionTitle`/`ShowAll` 元件，不新增設計語彙。
- 後端仍綁 `127.0.0.1`；不寫入 104。
- 加法式遷移：新表用 `CREATE TABLE IF NOT EXISTS`，既有 DB 重連即長出。
- 測試資料隔離：`tests/conftest.py` 已 autouse 把 `SENTINEL_DATA_DIR` 導向 tmp；明確自建 db（`store.connect(tmp)` / `create_app(db_path=…)`）的測試照常。

---

### Task 1: `tracked_jobs` 資料表 ＋ TrackedJob/PipelineJob models ＋ store 讀寫

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（在 `JobPreferences` 附近新增兩個 model）
- Modify: `sentinel/src/career_sentinel/store.py`（`_SCHEMA` 加表；新增三個函式）
- Test: `sentinel/tests/test_tracked_jobs_store.py`（新檔）

**Interfaces:**
- Produces:
  - `models.TrackedJob(code: str, company='', title='', url='', salary='', state='interested', match_score: int|None=None, created_at='', updated_at='')`
  - `models.PipelineJob(key: str, code='', company='', title='', state='interested', url='', salary='', match_score: int|None=None, status='', applied_at='', when='', location='', gcal_link='', interview_key='', dismissed=False, company_url='', job_url='', thread_url='', watched=False)`
  - `store.load_tracked_jobs(conn) -> list[TrackedJob]`
  - `store.upsert_tracked_job(conn, job: TrackedJob) -> None`
  - `store.get_tracked_job(conn, code: str) -> TrackedJob | None`

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_tracked_jobs_store.py`：

```python
from career_sentinel import store
from career_sentinel.models import TrackedJob


def test_upsert_and_load_tracked_jobs(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_tracked_jobs(conn) == []
    store.upsert_tracked_job(conn, TrackedJob(
        code="abc12", company="台積電", title="後端工程師", url="https://www.104.com.tw/job/abc12",
        salary="月薪 6 萬", state="tailored", match_score=82,
        created_at="2026-07-05T10:00:00", updated_at="2026-07-05T10:00:00",
    ))
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "abc12"
    assert jobs[0].state == "tailored"
    assert jobs[0].match_score == 82


def test_upsert_overwrites_same_code(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="matched", match_score=70))
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="tailored", match_score=88))
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1  # 同 code 覆寫、不重複
    assert jobs[0].state == "tailored"
    assert jobs[0].match_score == 88


def test_get_tracked_job_by_code(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.get_tracked_job(conn, "nope") is None
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="interested"))
    got = store.get_tracked_job(conn, "abc12")
    assert got is not None and got.state == "interested"


def test_match_score_none_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="x1"))  # match_score 預設 None
    assert store.get_tracked_job(conn, "x1").match_score is None


def test_old_db_gains_tracked_jobs_table(tmp_path):
    # 既有 DB 重連即長出新表（加法式遷移）
    p = tmp_path / "db.sqlite"
    store.connect(p).close()
    conn = store.connect(p)
    assert store.load_tracked_jobs(conn) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && python -m pytest tests/test_tracked_jobs_store.py -v`
Expected: FAIL（`ImportError: cannot import name 'TrackedJob'` 或 `AttributeError: module 'career_sentinel.store' has no attribute 'load_tracked_jobs'`）

- [ ] **Step 3: 加 models**

在 `sentinel/src/career_sentinel/models.py` 的 `JobPreferences` class 後面新增：

```python
class TrackedJob(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    state: str = "interested"   # interested|matched|tailored|offer|rejected
    match_score: int | None = None
    created_at: str = ""
    updated_at: str = ""


class PipelineJob(BaseModel):
    """合併引擎輸出的統一 DTO（前端據 state 分組渲染）。"""
    key: str                    # code；interview 無 code 時退回 company|job_title|when
    code: str = ""
    company: str = ""
    title: str = ""
    state: str = "interested"   # 有效狀態
    url: str = ""
    salary: str = ""
    match_score: int | None = None
    # 已投遞側（來自 applications）
    status: str = ""
    applied_at: str = ""
    # 面試側（來自 interviews）
    when: str = ""
    location: str = ""
    gcal_link: str = ""
    interview_key: str = ""
    dismissed: bool = False
    # 連結與旗標
    company_url: str = ""
    job_url: str = ""
    thread_url: str = ""
    watched: bool = False
```

- [ ] **Step 4: 加 `tracked_jobs` 表 schema**

在 `sentinel/src/career_sentinel/store.py` 的 `_SCHEMA` 字串內（`usage_log` 表定義之後、結尾 `"""` 之前）加：

```sql
CREATE TABLE IF NOT EXISTS tracked_jobs (
    code TEXT PRIMARY KEY,
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    salary TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'interested',
    match_score INTEGER,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
```

- [ ] **Step 5: 加 store 函式**

`store.py` 頂部 import 補上 `TrackedJob`（把它加入現有 `from .models import (...)` 清單，保持字母序附近即可）。在檔案結尾（`save_research` 之後）新增：

```python
def load_tracked_jobs(conn: sqlite3.Connection) -> list[TrackedJob]:
    rows = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at "
        "FROM tracked_jobs ORDER BY updated_at DESC"
    )
    return [
        TrackedJob(
            code=c, company=co, title=t, url=u, salary=sa, state=st,
            match_score=ms, created_at=ca, updated_at=ua,
        )
        for c, co, t, u, sa, st, ms, ca, ua in rows
    ]


def get_tracked_job(conn: sqlite3.Connection, code: str) -> TrackedJob | None:
    row = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at "
        "FROM tracked_jobs WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        return None
    c, co, t, u, sa, st, ms, ca, ua = row
    return TrackedJob(
        code=c, company=co, title=t, url=u, salary=sa, state=st,
        match_score=ms, created_at=ca, updated_at=ua,
    )


def upsert_tracked_job(conn: sqlite3.Connection, job: TrackedJob) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_jobs "
        "(code, company, title, url, salary, state, match_score, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (job.code, job.company, job.title, job.url, job.salary, job.state,
         job.match_score, job.created_at, job.updated_at),
    )
    conn.commit()
```

- [ ] **Step 6: 跑測試確認通過**

Run: `cd sentinel && python -m pytest tests/test_tracked_jobs_store.py -v`
Expected: PASS（5 passed）

- [ ] **Step 7: 全測試回歸**

Run: `cd sentinel && python -m pytest -q`
Expected: 全綠（新測試通過、既有測試不受影響）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_tracked_jobs_store.py
git commit -m "feat(sentinel): tracked_jobs 表 + TrackedJob/PipelineJob models + store 讀寫（SP15）"
```

---

### Task 2: `pipeline.py` 合併引擎（狀態機 ＋ build_pipeline）

**Files:**
- Create: `sentinel/src/career_sentinel/pipeline.py`
- Test: `sentinel/tests/test_pipeline.py`（新檔）

**Interfaces:**
- Consumes: `store.load_tracked_jobs`、`store.load_settings`、`store.load_dismissed`、`store.latest_two_ids`、`store.load_snapshot`（Task 1 ＋ 既有）；`company_link.job_url_from_raw/company_url_from_raw/chat_url_from_raw`、`calendar_link.build_gcal_link`、`jobfetch.extract_job_code`（raise `ValueError`）、`watch.is_watched`、`models.interview_key`、`models.PipelineJob`、`models.Snapshot`（既有）。
- Produces:
  - `pipeline.effective_state(manual: str | None, signal_rank: int) -> str`
  - `pipeline.build_pipeline(conn) -> list[PipelineJob]`
  - 模組常數 `pipeline.STATE_RANK: dict[str, int]`（`interested=1, matched=2, tailored=3, applied=4, interviewing=5`）、`pipeline.TERMINAL: set[str]`（`{"offer", "rejected"}`）

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_pipeline.py`：

```python
from career_sentinel import pipeline, store
from career_sentinel.models import (
    Application, Interview, Snapshot, TrackedJob,
)


def _conn_with(tmp_path, snap: Snapshot):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, snap, run_at="2026-07-05T10:00:00")
    return conn


# ---- effective_state 純函式 ----

def test_effective_state_signal_only():
    assert pipeline.effective_state(None, 4) == "applied"
    assert pipeline.effective_state(None, 5) == "interviewing"


def test_effective_state_takes_furthest():
    # 手動 tailored(3) 但 104 已 applied(4) → 取較前面的 applied
    assert pipeline.effective_state("tailored", 4) == "applied"
    # 手動 interested(1) 但 104 interviewing(5) → interviewing
    assert pipeline.effective_state("interested", 5) == "interviewing"


def test_effective_state_manual_only():
    assert pipeline.effective_state("matched", 0) == "matched"


def test_effective_state_terminal_overrides():
    # 手動 offer 覆蓋 104 的 interviewing
    assert pipeline.effective_state("offer", 5) == "offer"
    assert pipeline.effective_state("rejected", 4) == "rejected"


# ---- build_pipeline 整合 ----

def test_build_empty_db_returns_list(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")  # 無 snapshot
    assert pipeline.build_pipeline(conn) == []


def test_build_applications_become_applied(tmp_path):
    snap = Snapshot(applications=[
        Application(job_id="a1", company="甲", title="後端", status="已讀", applied_at="2026-07-01"),
    ])
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "a1"
    assert jobs[0].state == "applied"
    assert jobs[0].status == "已讀"


def test_build_interview_with_code(tmp_path):
    snap = Snapshot(interviews=[
        Interview(company="乙", job_title="前端", when="2026-07-10 14:00:00",
                  location="台北", job_url="https://www.104.com.tw/job/bb2cc"),
    ])
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "bb2cc"
    assert jobs[0].state == "interviewing"
    assert jobs[0].gcal_link  # 有帶 gcal 連結
    assert jobs[0].when == "2026-07-10 14:00:00"


def test_build_interview_without_code_uses_fallback_key(tmp_path):
    snap = Snapshot(interviews=[
        Interview(company="丙", job_title="PM", when="2026-07-11 09:00:00", location="遠端", job_url=""),
    ])
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == ""
    assert jobs[0].key == "丙|PM|2026-07-11 09:00:00"
    assert jobs[0].state == "interviewing"


def test_build_merges_same_code_application_and_interview(tmp_path):
    snap = Snapshot(
        applications=[Application(job_id="dd3ee", company="丁", title="資料", status="已讀", applied_at="2026-07-01")],
        interviews=[Interview(company="丁", job_title="資料", when="2026-07-12 10:00:00",
                              location="台中", job_url="https://www.104.com.tw/job/dd3ee")],
    )
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1  # 同 code 併成一筆
    assert jobs[0].state == "interviewing"  # 取較前面
    assert jobs[0].status == "已讀"          # application 欄位仍保留
    assert jobs[0].when == "2026-07-12 10:00:00"


def test_build_tracked_terminal_overrides_signal(tmp_path):
    snap = Snapshot(interviews=[
        Interview(company="戊", job_title="後端", when="2026-07-13 10:00:00",
                  location="台北", job_url="https://www.104.com.tw/job/ff4gg"),
    ])
    conn = _conn_with(tmp_path, snap)
    store.upsert_tracked_job(conn, TrackedJob(code="ff4gg", state="offer", salary="年薪 120 萬"))
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].state == "offer"        # 終端手動覆蓋 interviewing
    assert jobs[0].salary == "年薪 120 萬"  # tracked 欄位帶入


def test_build_tracked_only_job_appears(tmp_path):
    # tracked_jobs 有、104 完全沒有的職缺也要進清單
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="gg5hh", company="己", title="設計", state="matched", match_score=75))
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "gg5hh"
    assert jobs[0].state == "matched"
    assert jobs[0].match_score == 75


def test_build_swallows_errors(tmp_path, monkeypatch):
    conn = store.connect(tmp_path / "db.sqlite")
    monkeypatch.setattr(store, "load_tracked_jobs", lambda c: (_ for _ in ()).throw(RuntimeError("boom")))
    assert pipeline.build_pipeline(conn) == []  # best-effort：吞例外回空清單
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && python -m pytest tests/test_pipeline.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'career_sentinel.pipeline'`）

- [ ] **Step 3: 實作 `pipeline.py`**

建立 `sentinel/src/career_sentinel/pipeline.py`：

```python
"""職缺管道合併引擎（SP15）。

純讀、best-effort：把最新 snapshot 的 applications/interviews 與 tracked_jobs
（手動層）用 104 job code 併成一份 PipelineJob 清單，算出每筆的有效狀態。
任何例外都吞掉回空清單，絕不影響 snapshot / scrape。
"""
from __future__ import annotations

import sqlite3

from . import calendar_link, company_link, jobfetch, store, watch
from .models import PipelineJob, Snapshot, interview_key

STATE_RANK: dict[str, int] = {
    "interested": 1,
    "matched": 2,
    "tailored": 3,
    "applied": 4,
    "interviewing": 5,
}
TERMINAL: set[str] = {"offer", "rejected"}
_RANK_NAME = {r: name for name, r in STATE_RANK.items()}


def effective_state(manual: str | None, signal_rank: int) -> str:
    """manual：tracked_jobs.state（可 None）；signal_rank：104 訊號 rank（0=無）。
    終端手動狀態優先；否則取兩者較前面的狀態名。"""
    if manual in TERMINAL:
        return manual  # type: ignore[return-value]
    manual_rank = STATE_RANK.get(manual or "", 0)
    best = max(manual_rank, signal_rank)
    return _RANK_NAME.get(best, "interested")


def build_pipeline(conn: sqlite3.Connection) -> list[PipelineJob]:
    try:
        return _build(conn)
    except Exception:
        return []


def _build(conn: sqlite3.Connection) -> list[PipelineJob]:
    settings = store.load_settings(conn)
    dismissed = set(store.load_dismissed(conn).keys)
    ids = store.latest_two_ids(conn)
    snap = store.load_snapshot(conn, ids[0]) if ids else Snapshot()

    jobs: dict[str, PipelineJob] = {}
    signal: dict[str, int] = {}  # key -> 104 訊號 rank

    # applications → applied(4)
    for a in snap.applications:
        key = a.job_id or f"app|{a.company}|{a.title}"
        pj = jobs.setdefault(key, PipelineJob(key=key))
        pj.code = a.job_id or pj.code
        pj.company = a.company or pj.company
        pj.title = a.title or pj.title
        pj.status = a.status
        pj.applied_at = a.applied_at
        pj.job_url = company_link.job_url_from_raw(a.raw) or pj.job_url
        pj.company_url = company_link.company_url_from_raw(a.raw) or pj.company_url
        pj.watched = watch.is_watched(a.company, a.title, settings)
        signal[key] = max(signal.get(key, 0), STATE_RANK["applied"])

    # interviews → interviewing(5)
    for iv in snap.interviews:
        try:
            code = jobfetch.extract_job_code(iv.job_url)
        except ValueError:
            code = ""
        key = code or interview_key(iv)
        pj = jobs.setdefault(key, PipelineJob(key=key))
        pj.code = code or pj.code
        pj.company = iv.company or pj.company
        pj.title = iv.job_title or pj.title
        pj.when = iv.when
        pj.location = iv.location
        pj.gcal_link = calendar_link.build_gcal_link(iv)
        pj.interview_key = interview_key(iv)
        pj.dismissed = interview_key(iv) in dismissed
        pj.job_url = iv.job_url or pj.job_url
        pj.company_url = company_link.company_url_from_raw(iv.raw) or pj.company_url
        pj.thread_url = company_link.chat_url_from_raw(iv.raw) or pj.thread_url
        signal[key] = max(signal.get(key, 0), STATE_RANK["interviewing"])

    # tracked_jobs 手動層：併入既有 job 或新增純手動 job
    manual = {tj.code: tj for tj in store.load_tracked_jobs(conn)}
    for key, pj in jobs.items():
        tj = manual.get(pj.code) or manual.get(key)
        if tj is not None:
            pj.url = tj.url or pj.url
            pj.salary = tj.salary or pj.salary
            if tj.match_score is not None:
                pj.match_score = tj.match_score
            pj.company = pj.company or tj.company
            pj.title = pj.title or tj.title
        pj.state = effective_state(tj.state if tj else None, signal.get(key, 0))

    seen_codes = {pj.code for pj in jobs.values() if pj.code}
    for code, tj in manual.items():
        if not code or code in jobs or code in seen_codes:
            continue
        pj = PipelineJob(
            key=code, code=code, company=tj.company, title=tj.title,
            url=tj.url, salary=tj.salary, match_score=tj.match_score,
        )
        pj.state = effective_state(tj.state, 0)
        jobs[code] = pj

    return list(jobs.values())
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && python -m pytest tests/test_pipeline.py -v`
Expected: PASS（全部通過）

- [ ] **Step 5: 全測試回歸**

Run: `cd sentinel && python -m pytest -q`
Expected: 全綠

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/pipeline.py sentinel/tests/test_pipeline.py
git commit -m "feat(sentinel): pipeline 合併引擎 + 狀態機（SP15）"
```

---

### Task 3: `/api/snapshot` 輸出 `pipeline`（best-effort）

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`（`_snapshot_payload`，約 52-86 行）
- Test: `sentinel/tests/test_web_pipeline.py`（新檔）

**Interfaces:**
- Consumes: `pipeline.build_pipeline(conn) -> list[PipelineJob]`（Task 2）。
- Produces: `/api/snapshot` JSON 多一個 `"pipeline": list[dict]` 欄位；既有欄位不變。空 DB 時 `pipeline == []`。

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_web_pipeline.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel import store
from career_sentinel.web import app as webapp
from career_sentinel.models import Application, Interview, Snapshot


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_snapshot_empty_has_pipeline_key(tmp_path):
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["pipeline"] == []
    # 既有欄位保留
    assert body["applications"] == [] and body["interviews"] == []


def test_snapshot_pipeline_from_scrape(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        applications=[Application(job_id="a1", company="甲", title="後端", status="已讀", applied_at="2026-07-01")],
        interviews=[Interview(company="乙", job_title="前端", when="2026-07-10 14:00:00",
                              location="台北", job_url="https://www.104.com.tw/job/bb2cc")],
    ), run_at="2026-07-05T10:00:00")
    body = _client(tmp_path).get("/api/snapshot").json()
    states = {j["code"]: j["state"] for j in body["pipeline"]}
    assert states["a1"] == "applied"
    assert states["bb2cc"] == "interviewing"


def test_snapshot_survives_pipeline_error(tmp_path, monkeypatch):
    # build_pipeline 丟例外時，snapshot 其他欄位仍完整、pipeline 回 []
    from career_sentinel import pipeline
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        applications=[Application(job_id="a1", company="甲", title="後端", status="已讀", applied_at="2026-07-01")],
    ), run_at="2026-07-05T10:00:00")
    monkeypatch.setattr(pipeline, "build_pipeline", lambda c: (_ for _ in ()).throw(RuntimeError("boom")))
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["pipeline"] == []
    assert body["applications"][0]["job_id"] == "a1"  # 其他欄位不受影響
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && python -m pytest tests/test_web_pipeline.py -v`
Expected: FAIL（`KeyError: 'pipeline'`）

- [ ] **Step 3: 接上 pipeline**

在 `sentinel/src/career_sentinel/web/app.py` 頂部 import 區加入 `pipeline`（與其他 `from career_sentinel import ...` 同區；模組匯入慣例：`from .. import pipeline` 或跟隨該檔既有 sentinel 模組匯入寫法）。

在 `_snapshot_payload(conn)` 內定義一個 best-effort 區塊，並把它塞進兩個 return dict。具體做法：在函式開頭（`failed = ...` 之後）算好 pipeline，兩個 return 都帶：

```python
def _snapshot_payload(conn) -> dict:
    failed = runner.status()["last_failed_readers"]
    try:
        pipeline_jobs = [pj.model_dump() for pj in pipeline.build_pipeline(conn)]
    except Exception:
        pipeline_jobs = []
    ids = store.latest_two_ids(conn)
    if not ids:
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [], "interviews": [],
            "pipeline": pipeline_jobs,
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": failed,
        }
    sid = ids[0]
    snap = store.load_snapshot(conn, sid)
    d = diff.diff_against_last(conn, sid)
    settings = store.load_settings(conn)
    dismissed = set(store.load_dismissed(conn).keys)
    return {
        "run_at": store.latest_run_at(conn),
        "viewers": [ ... 既有不動 ... ],
        "applications": [ ... 既有不動 ... ],
        "messages": [ ... 既有不動 ... ],
        "interviews": [ ... 既有不動 ... ],
        "pipeline": pipeline_jobs,
        "digest": digest.render_human(d, snap),
        "failed_readers": failed,
    }
```

> 只需：(1) import `pipeline`；(2) 在函式頂部加 `try/except` 算 `pipeline_jobs`；(3) 兩個 return dict 各加一行 `"pipeline": pipeline_jobs,`。既有 viewers/applications/messages/interviews 的 list comprehension **原封不動**。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && python -m pytest tests/test_web_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: 全測試回歸**

Run: `cd sentinel && python -m pytest -q`
Expected: 全綠（既有 `test_web_app.py` 的 snapshot 測試仍通過，因為只是多欄位）

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_pipeline.py
git commit -m "feat(sentinel): /api/snapshot 輸出 pipeline（best-effort）（SP15）"
```

---

### Task 4: 前端求職中心（api.ts 型別 ＋ Dashboard 管道分組）

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（`SnapshotResp` 加 `pipeline`；新增 `PipelineJob` interface）
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`（把「即將到來的面試」＋「我的應徵」重排成按狀態分組的管道；誰看過我/訊息移到下方）
- 驗證：`sentinel/web/frontend` 下 `npm run build`（tsc 型別檢查 ＋ vite build）

**Interfaces:**
- Consumes: `/api/snapshot` 的 `pipeline` 欄位（Task 3），每筆型別見下 `PipelineJob`。
- Produces: 求職中心版面：上 KPI（不動）→ 職缺管道（面試中/已投遞 群組）→ 次要訊號區（誰看過我、訊息）。

- [ ] **Step 1: api.ts 加型別**

在 `sentinel/web/frontend/src/api.ts` 的 `SnapshotResp` 定義前新增 interface，並在 `SnapshotResp` 加 `pipeline` 欄位：

```typescript
export interface PipelineJob {
  key: string;
  code: string;
  company: string;
  title: string;
  state: string;        // interested|matched|tailored|applied|interviewing|offer|rejected
  url: string;
  salary: string;
  match_score: number | null;
  status: string;
  applied_at: string;
  when: string;
  location: string;
  gcal_link: string;
  interview_key: string;
  dismissed: boolean;
  company_url: string;
  job_url: string;
  thread_url: string;
  watched: boolean;
}
```

並把 `SnapshotResp` 改成含 `pipeline: PipelineJob[];`：

```typescript
export interface SnapshotResp {
  run_at: string | null;
  viewers: Viewer[];
  applications: Application[];
  messages: Message[];
  interviews: Interview[];
  pipeline: PipelineJob[];
  digest: string;
  failed_readers: string[];
}
```

- [ ] **Step 2: Dashboard 匯入與資料準備**

在 `sentinel/web/frontend/src/Dashboard.tsx`：

- import 補 `PipelineJob` 型別：把第 5 行改為
  ```typescript
  import { type Interview, type PipelineJob, dismissInterview, getSnapshot, getStatus, restoreInterview } from "./api";
  ```
- 在既有 `const upcoming = ...` / `const doneIvs = ...` 附近，用 `pipeline` 算出各群組（面試中拆成未處理/已處理，沿用 dismissed）：
  ```typescript
  const pipe = s?.pipeline ?? [];
  const interviewing = pipe.filter((j) => j.state === "interviewing");
  const upcomingJobs = interviewing.filter((j) => !j.dismissed);
  const doneJobs = interviewing.filter((j) => j.dismissed);
  const appliedJobs = pipe.filter((j) => j.state === "applied");
  ```
  （KPI 區維持讀 `s.viewers/interviews/messages/applications`，不動。既有 `upcoming`/`doneIvs`/`allApps`/`apps` 若僅供舊區塊使用，於本任務改寫區塊後一併移除，避免 unused。）

- [ ] **Step 3: 用管道群組取代「即將到來的面試」＋「我的應徵」區塊**

把現在的「即將到來的面試」`<div style={{ marginTop: 32 }}>…</div>` 區塊（約 132-185 行）與 Grid 右欄「我的應徵」`sec-applications` 區塊（約 206-226 行），改成一個「職缺管道」區塊。面試中群組每筆用 `PipelineJob`，**完整保留 SP7 功能**（gcal / 知道了-還原 / 看職缺 / 對話串 / 已處理收合）。以下為職缺管道區塊（取代原「即將到來的面試」整段；已投遞群組取代原 `sec-applications`）：

```tsx
{s && (upcomingJobs.length > 0 || appliedJobs.length > 0 || doneJobs.length > 0) && (
  <div style={{ marginTop: 32 }}>
    <SectionTitle id="sec-pipeline">職缺管道</SectionTitle>

    {upcomingJobs.length > 0 && (
      <>
        <Text size="xs" c="teal.5" mb={6} mt="xs" fw={600} style={{ letterSpacing: 1 }}>面試中</Text>
        {upcomingJobs.map((j: PipelineJob) => (
          <Row key={j.key}>
            <Text size="sm" truncate style={{ minWidth: 0, flex: 1 }}>
              <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
              <Text span c="dimmed"> · {j.title}{j.location ? ` · ${j.location}` : ""}</Text>
            </Text>
            <ResearchButton company={j.company} />
            <Group gap="md" wrap="nowrap" style={{ flexShrink: 0 }}>
              <Text c="teal.5" ff="monospace" size="xs">{j.when || "日期未擷取"}</Text>
              {j.job_url && <Anchor href={j.job_url} target="_blank" size="xs" c="dimmed">看職缺</Anchor>}
              {j.thread_url && (
                <ActionIcon component="a" href={j.thread_url} target="_blank"
                  variant="default" size="md" title="開啟 104 對話">
                  <IconMessageCircle size={15} />
                </ActionIcon>
              )}
              <ActionIcon component="a" href={j.gcal_link} target="_blank"
                variant="default" size="md" title="加入 Google 日曆">
                <IconCalendarPlus size={15} />
              </ActionIcon>
              <ActionIcon variant="default" size="md" title="知道了（隱藏，可還原）"
                onClick={ackInterview(j.interview_key)}>
                <IconCheck size={15} />
              </ActionIcon>
            </Group>
          </Row>
        ))}
      </>
    )}

    {doneJobs.length > 0 && (
      <>
        <Button variant="subtle" color="gray" size="compact-xs" onClick={() => setShowDone((v) => !v)}>
          {showDone ? "收合已處理" : `已處理 ${doneJobs.length} 場`}
        </Button>
        {showDone && doneJobs.map((j: PipelineJob) => (
          <Row key={j.key}>
            <Text size="sm" truncate style={{ opacity: 0.55, minWidth: 0, flex: 1 }}>
              <Text span fw={600}>{j.company}</Text>
              <Text span c="dimmed"> · {j.title} · {j.when || "日期未擷取"}</Text>
            </Text>
            <ActionIcon variant="subtle" color="gray" size="md" title="還原到清單" style={{ flexShrink: 0 }}
              onClick={unackInterview(j.interview_key)}>
              <IconArrowBackUp size={15} />
            </ActionIcon>
          </Row>
        ))}
      </>
    )}

    {appliedJobs.length > 0 && (
      <>
        <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>已投遞</Text>
        {appliedJobs.map((j: PipelineJob) => (
          <Row key={j.key}>
            <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
              {j.watched && <Star />}
              <Text size="sm" truncate>
                <CompanyLink name={j.company} href={j.company_url || undefined} />
                <Text span c="dimmed"> · </Text>
                {j.job_url ? (
                  <Anchor href={j.job_url} target="_blank" size="sm" c="dimmed" underline="hover">{j.title}</Anchor>
                ) : (
                  <Text span c="dimmed">{j.title}</Text>
                )}
              </Text>
              <ResearchButton company={j.company} />
            </Group>
            {j.status && <Badge size="sm" variant="light" color="teal">{j.status}</Badge>}
          </Row>
        ))}
      </>
    )}
  </div>
)}
```

> `ackInterview`/`unackInterview` 既有簽名是 `(key: string) => async () => {...}`，這裡改傳 `j.interview_key`（面試群組必有值）。這兩個 helper 內容不變。

- [ ] **Step 4: 誰看過我/訊息移到管道下方（次要訊號區）**

把原本 `<Grid mt={32} gutter={36}>` 兩欄版面改成管道下方的次要訊號區。保留「誰看過我」與「訊息·面試」兩區塊、沿用 `Row`/`ShowAll`/`ResearchButton`，只是移到職缺管道之後、仍用 Grid 兩欄即可：

```tsx
<Grid mt={32} gutter={36}>
  <Grid.Col span={6}>
    <SectionTitle id="sec-viewers">誰看過我</SectionTitle>
    {viewers.map((v, i) => (
      <Row key={i}>
        <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
          {v.watched && <Star />}
          <Text size="sm" truncate>
            <CompanyLink name={v.company} href={v.company_url || undefined} />
            <Text span c="dimmed"> · {v.job_title}</Text>
          </Text>
          <ResearchButton company={v.company} />
        </Group>
        <Text c="dimmed" ff="monospace" size="xs">{v.viewed_at}</Text>
      </Row>
    ))}
    <ShowAll total={s?.viewers.length ?? 0} showAll={allViewers} onToggle={() => setAllViewers((v) => !v)} />
  </Grid.Col>

  <Grid.Col span={6}>
    <SectionTitle id="sec-messages">訊息 · 面試</SectionTitle>
    {msgs.map((m) => (
      <Row key={m.thread_id}>
        <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
          {m.has_interview_invite && <Badge size="xs" variant="light" color="amber">面試</Badge>}
          {m.watched && <Star />}
          <Text size="sm" truncate>
            <CompanyLink name={m.company} href={m.company_url || undefined} />
            <Text span c="dimmed">：{m.last_message}</Text>
          </Text>
          <ResearchButton company={m.company} />
        </Group>
        {m.thread_url && (
          <ActionIcon component="a" href={m.thread_url} target="_blank"
            variant="subtle" color="gray" size="sm" title="開啟 104 對話" style={{ flexShrink: 0 }}>
            <IconMessageCircle size={14} />
          </ActionIcon>
        )}
      </Row>
    ))}
    <ShowAll total={s?.messages.length ?? 0} showAll={allMsgs} onToggle={() => setAllMsgs((v) => !v)} />
  </Grid.Col>
</Grid>
```

> 移除舊的 `sec-interviews` 區塊與 `sec-applications` 區塊（其功能已由職缺管道涵蓋）。`allApps`/`apps` state 與 `upcoming`/`doneIvs` 變數若不再被引用，一併刪除以免 TypeScript unused 警告（`tsc -b` 於 `noUnusedLocals` 下會報錯）。「今日彙整」digest 區塊與 KPI 區塊維持不動。

- [ ] **Step 5: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功（`tsc -b` 無型別/unused 錯誤、`vite build` 產出 dist）。若報 unused 變數，回 Step 4 刪除殘留的 `upcoming`/`doneIvs`/`allApps`/`apps`/`setAllApps`。

- [ ] **Step 6: 全後端測試回歸（確認沒動到後端契約）**

Run: `cd sentinel && python -m pytest -q`
Expected: 全綠。

- [ ] **Step 7: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 儀表板擴張成求職中心（職缺管道分組 + 訊號區）（SP15）"
```

---

## Self-Review 註記（計畫作者）

- **Spec coverage：** 資料表(Task1)、狀態機＋合併引擎(Task2)、API 輸出(Task3)、求職中心版面＋面試功能保留(Task4) 全覆蓋。offer/婉拒終端狀態的顯示留 SP18，但 `effective_state` 已支援終端覆蓋（Task2 有測）。
- **型別一致：** `PipelineJob` 欄位在 models.py(Task1)、pipeline.py(Task2)、api.ts(Task4) 三處一致；`effective_state`/`build_pipeline`/`STATE_RANK`/`TERMINAL` 命名跨任務一致。
- **邊界：** interview 無 code 走 `interview_key` 退回鍵（Task2 有測）；`extract_job_code` raise `ValueError` 已用 try/except 接住（spec 原寫「回空字串」，實際是 raise，計畫已修正為 try/except）。
- **best-effort：** `build_pipeline` 內層 `_build` ＋ 外層吞例外；payload 再包一層 try/except（雙重防護，Task2、Task3 各有測）。
