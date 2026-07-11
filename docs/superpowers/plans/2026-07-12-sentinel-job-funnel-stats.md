# 求職漏斗 / 進度統計儀表板 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 career-sentinel 加一頁「求職統計」：狀態事件 log 支撐的各階段停留天數、累積達到漏斗、階段轉換率與停滯提醒。

**Architecture:** 新增輕量 `state_events` 表（只在狀態真的改變時記一筆）＋ backfill；新 `stats.py` 純函式做聚合（可單測）；`/api/stats` 掛在 dashboard router；前端新開 `StatsPage`（純 CSS 長條、不加圖表套件）。

**Tech Stack:** Python 3.12、sqlite、Pydantic v2、FastAPI；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- 停留天數只做使用者可控狀態（interested/matched/tailored/offer/rejected）；applied/interviewing 只計入漏斗與轉換率、不做停留。
- 漏斗用「累積達到 `reached(state)`」語意（單調遞減）；`rejected` 不進漏斗與 reached，只呈現於 `rejected_count`。
- 轉換率百分比為 0–100 整數，分母 0 → `None`（前端顯示「—」）。
- 狀態事件只在「最終狀態 ≠ 舊狀態或首次」時寫入（scrape 沿用寫入不記）。
- 停滯門檻常數 `STALE_DAYS = 14`，排除終端狀態（offer/rejected）。
- 不引入前端圖表套件（純 CSS 長條）。時間解析壞值以 try/except 跳過單筆、不炸整頁。
- 測試用專案 venv：`./.venv/Scripts/python.exe -m pytest -q`（工作目錄 `sentinel/`）。前端 `cd web/frontend && npm run build`。
- 不改既有管道頁 / 儀表板既有區塊。

---

## 檔案結構

```
src/career_sentinel/
├─ models.py           # + class StateEvent
├─ store.py            # + state_events 表/函式/logging/backfill
├─ stats.py            # 新：compute_stats 聚合
└─ web/routers/dashboard.py   # + GET /api/stats
web/frontend/src/
├─ api.ts              # + StatsResp 型別 + getStats()
├─ StatsPage.tsx       # 新：統計頁
├─ Sidebar.tsx         # + nav「求職統計」、PageKey += "stats"
└─ App.tsx             # + 掛載 StatsPage
tests/
├─ test_tracked_jobs_store.py  # + 事件 logging/backfill/delete 測試
├─ test_stats.py       # 新：compute_stats 測試
└─ test_web_stats.py   # 新：/api/stats 端點測試
```

---

### Task 1: 資料層 — `state_events` 表、事件 logging、backfill

**Files:**
- Modify: `src/career_sentinel/models.py`（加 `StateEvent`）
- Modify: `src/career_sentinel/store.py`（schema、函式、logging、backfill、delete 連動）
- Test: `tests/test_tracked_jobs_store.py`

**Interfaces:**
- Produces:
  - `models.StateEvent(code: str, state: str, at: str)`
  - `store.append_state_event(conn, code: str, state: str, at: str) -> None`
  - `store.load_state_events(conn) -> list[StateEvent]`（依 `at, id` 升冪）
  - `store._backfill_state_events(conn) -> None`（冪等）
  - `merge_tracked_job` / `set_tracked_state` 在狀態變更時自動記事件；`delete_tracked_job` 連帶刪事件。

- [ ] **Step 1: 加 `StateEvent` model**

在 `src/career_sentinel/models.py` 的 `class TrackedJob` 之前加入：

```python
class StateEvent(BaseModel):
    code: str
    state: str
    at: str      # ISO 秒；狀態進入時間
```

- [ ] **Step 2: 寫失敗測試（事件 logging / backfill / delete）**

在 `tests/test_tracked_jobs_store.py` 末尾加入（若檔頭尚未 import，補 `from career_sentinel import store`；用既有的 `tmp_path` 連線風格）：

```python
def test_merge_logs_event_only_on_change(tmp_path):
    from career_sentinel import store
    conn = store.connect(str(tmp_path / "db.sqlite"))
    store.merge_tracked_job(conn, "a", state="interested", company="甲")
    store.merge_tracked_job(conn, "a", state="interested")  # 狀態沒變 → 不記
    store.merge_tracked_job(conn, "a", state="matched", match_score=80)  # 進階 → 記
    evs = [e for e in store.load_state_events(conn) if e.code == "a"]
    assert [e.state for e in evs] == ["interested", "matched"]


def test_set_tracked_state_logs_on_change(tmp_path):
    from career_sentinel import store
    conn = store.connect(str(tmp_path / "db.sqlite"))
    store.merge_tracked_job(conn, "b", state="interested")
    store.set_tracked_state(conn, "b", "rejected")
    store.set_tracked_state(conn, "b", "rejected")  # 同狀態 → 不記
    evs = [e for e in store.load_state_events(conn) if e.code == "b"]
    assert [e.state for e in evs] == ["interested", "rejected"]


def test_delete_removes_state_events(tmp_path):
    from career_sentinel import store
    conn = store.connect(str(tmp_path / "db.sqlite"))
    store.merge_tracked_job(conn, "c", state="interested")
    store.delete_tracked_job(conn, "c")
    assert [e for e in store.load_state_events(conn) if e.code == "c"] == []


def test_backfill_is_idempotent(tmp_path):
    from career_sentinel import store
    from career_sentinel.models import TrackedJob
    conn = store.connect(str(tmp_path / "db.sqlite"))
    # 直接 upsert（不經 merge/set）→ 模擬升級前的舊資料，無事件
    store.upsert_tracked_job(conn, TrackedJob(code="d", state="tailored",
                                              created_at="2026-07-01T09:00:00", updated_at="2026-07-01T09:00:00"))
    assert [e for e in store.load_state_events(conn) if e.code == "d"] == []
    store._backfill_state_events(conn)
    store._backfill_state_events(conn)  # 再跑一次仍只有一筆
    evs = [e for e in store.load_state_events(conn) if e.code == "d"]
    assert len(evs) == 1 and evs[0].state == "tailored" and evs[0].at == "2026-07-01T09:00:00"
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: FAIL（`append_state_event`/`load_state_events`/`_backfill_state_events` 不存在，或事件未記）

- [ ] **Step 4: 加 `state_events` 表到 `_SCHEMA`**

在 `store.py` 的 `_SCHEMA` 字串內（`tracked_jobs` CREATE 之後、結尾 `"""` 之前）加入：

```sql
CREATE TABLE IF NOT EXISTS state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    state TEXT NOT NULL,
    at TEXT NOT NULL
);
```

- [ ] **Step 5: 加事件函式與 backfill，並在 `connect()` 呼叫 backfill**

在 `store.py` 匯入區把 `StateEvent` 加進 `from .models import (...)`。在 `delete_tracked_job` 之後（或檔案 tracked 區塊附近）加入：

```python
def append_state_event(conn: sqlite3.Connection, code: str, state: str, at: str) -> None:
    conn.execute("INSERT INTO state_events (code, state, at) VALUES (?, ?, ?)", (code, state, at))
    conn.commit()


def load_state_events(conn: sqlite3.Connection) -> list[StateEvent]:
    rows = conn.execute("SELECT code, state, at FROM state_events ORDER BY at ASC, id ASC")
    return [StateEvent(code=c, state=s, at=a) for c, s, a in rows]


def _backfill_state_events(conn: sqlite3.Connection) -> None:
    """對既有 tracked_jobs 但無事件者，補一筆合成事件（現狀態 + created_at/updated_at）。冪等。"""
    rows = conn.execute(
        "SELECT t.code, t.state, t.created_at, t.updated_at FROM tracked_jobs t "
        "WHERE NOT EXISTS (SELECT 1 FROM state_events e WHERE e.code = t.code)"
    ).fetchall()
    for code, state, created_at, updated_at in rows:
        at = created_at or updated_at or datetime.now().isoformat(timespec="seconds")
        conn.execute("INSERT INTO state_events (code, state, at) VALUES (?, ?, ?)", (code, state, at))
    if rows:
        conn.commit()
```

在 `connect()` 內、`_migrate_preferences(conn)` 之後加一行 `_backfill_state_events(conn)`：

```python
def connect(path: Path | str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    _migrate(conn)
    _migrate_preferences(conn)
    _backfill_state_events(conn)
    return conn
```

- [ ] **Step 6: 在 `merge_tracked_job` / `set_tracked_state` 記事件、`delete_tracked_job` 連動刪除**

`merge_tracked_job`：在 `upsert_tracked_job(...)` 呼叫之後、`return final_state` 之前插入：

```python
    if existing is None or final_state != existing.state:
        append_state_event(conn, code, final_state, now)
```

`set_tracked_state`：在兩個 `upsert_tracked_job(...)` 分支之後、`return state` 之前插入：

```python
    if existing is None or state != existing.state:
        append_state_event(conn, code, state, now)
```

`delete_tracked_job`：改為連帶刪除事件：

```python
def delete_tracked_job(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("DELETE FROM tracked_jobs WHERE code = ?", (code,))
    conn.execute("DELETE FROM state_events WHERE code = ?", (code,))
    conn.commit()
```

- [ ] **Step 7: 跑測試確認通過（含全套回歸）**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 既有全綠 + 4 個新測試通過。

- [ ] **Step 8: Commit**

```bash
git add src/career_sentinel/models.py src/career_sentinel/store.py tests/test_tracked_jobs_store.py
git commit -m "feat(sentinel): 狀態事件 log（state_events 表 + 變更時記錄 + backfill）"
```

---

### Task 2: 聚合層 — `stats.py`

**Files:**
- Create: `src/career_sentinel/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `store.load_state_events`、`store.load_tracked_jobs`、`store.merge_tracked_job`/`set_tracked_state`（測試種資料用）、`pipeline.build_pipeline`。
- Produces: `stats.compute_stats(conn) -> stats.StatsResult`，欄位：
  - `funnel: list[FunnelStage{state,label,count}]`
  - `rejected_count: int`
  - `conversions: Conversions{applied_to_interview,interview_to_offer,interested_to_offer: int|None}`
  - `dwell: list[DwellStat{state,label,median_days: int|None, sample:int}]`
  - `stale: list[StaleJob{code,company,title,state,label,days_since_update:int,url}]`
  - 常數 `STALE_DAYS = 14`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_stats.py`：

```python
from datetime import datetime, timedelta

from career_sentinel import stats, store


def _conn(tmp_path):
    return store.connect(str(tmp_path / "db.sqlite"))


def test_funnel_reached_is_monotonic(tmp_path):
    conn = _conn(tmp_path)
    store.merge_tracked_job(conn, "a", state="interested")
    store.merge_tracked_job(conn, "b", state="matched")
    store.set_tracked_state(conn, "c", "offer")
    r = stats.compute_stats(conn)
    counts = {f.state: f.count for f in r.funnel}
    # reached：interested 計全部非 rejected(3)、matched≥2(2)、offer(1)
    assert counts["interested"] == 3
    assert counts["matched"] == 2
    assert counts["offer"] == 1
    # 單調遞減
    seq = [f.count for f in r.funnel]
    assert seq == sorted(seq, reverse=True)


def test_rejected_excluded_from_funnel(tmp_path):
    conn = _conn(tmp_path)
    store.merge_tracked_job(conn, "a", state="interested")
    store.set_tracked_state(conn, "b", "rejected")
    r = stats.compute_stats(conn)
    assert r.rejected_count == 1
    assert {f.state: f.count for f in r.funnel}["interested"] == 1  # rejected 不計入


def test_conversions_and_zero_denominator(tmp_path):
    conn = _conn(tmp_path)
    # 只有一個 interested → applied 分母 0
    store.merge_tracked_job(conn, "a", state="interested")
    r = stats.compute_stats(conn)
    assert r.conversions.applied_to_interview is None
    assert r.conversions.interested_to_offer == 0  # 分母 1、offer 0


def test_dwell_median_from_events(tmp_path):
    conn = _conn(tmp_path)
    # 手動塞事件：interested 停 2 天後進 matched
    store.append_state_event(conn, "x", "interested", "2026-07-01T00:00:00")
    store.append_state_event(conn, "x", "matched", "2026-07-03T00:00:00")
    store.append_state_event(conn, "y", "interested", "2026-07-01T00:00:00")
    store.append_state_event(conn, "y", "matched", "2026-07-05T00:00:00")  # 停 4 天
    r = stats.compute_stats(conn)
    d = {x.state: x for x in r.dwell}
    assert d["interested"].sample == 2
    assert d["interested"].median_days == 3   # (2,4) 中位數 3


def test_stale_over_threshold_excludes_terminal(tmp_path):
    conn = _conn(tmp_path)
    old = (datetime.now() - timedelta(days=20)).isoformat(timespec="seconds")
    from career_sentinel.models import TrackedJob
    store.upsert_tracked_job(conn, TrackedJob(code="s", company="甲", title="後端",
                                              state="interested", created_at=old, updated_at=old))
    store.upsert_tracked_job(conn, TrackedJob(code="o", state="offer", created_at=old, updated_at=old))
    r = stats.compute_stats(conn)
    codes = [j.code for j in r.stale]
    assert "s" in codes and "o" not in codes  # 終端狀態排除
    assert next(j for j in r.stale if j.code == "s").days_since_update >= 20
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stats.py -q`
Expected: FAIL（`career_sentinel.stats` 不存在）

- [ ] **Step 3: 實作 `stats.py`**

建立 `src/career_sentinel/stats.py`：

```python
"""求職統計聚合：漏斗（累積達到）、轉換率、各階段停留、停滯提醒。純資料、可單測。"""
from __future__ import annotations

from datetime import datetime
from statistics import median

from pydantic import BaseModel

from . import pipeline, store

STALE_DAYS = 14

_LABELS: dict[str, str] = {
    "interested": "有興趣", "matched": "已比對", "tailored": "已客製化",
    "applied": "已投遞", "interviewing": "面試中", "offer": "offer", "rejected": "未錄取",
}
_FUNNEL_ORDER = ["interested", "matched", "tailored", "applied", "interviewing", "offer"]
_DWELL_STATES = ["interested", "matched", "tailored", "offer", "rejected"]
# offer 視為 6（高於 interviewing 的 5）；rejected 不參與 reached
_RANK = {"interested": 1, "matched": 2, "tailored": 3, "applied": 4, "interviewing": 5, "offer": 6}


class FunnelStage(BaseModel):
    state: str
    label: str
    count: int


class Conversions(BaseModel):
    applied_to_interview: int | None = None
    interview_to_offer: int | None = None
    interested_to_offer: int | None = None


class DwellStat(BaseModel):
    state: str
    label: str
    median_days: int | None
    sample: int


class StaleJob(BaseModel):
    code: str
    company: str
    title: str
    state: str
    label: str
    days_since_update: int
    url: str


class StatsResult(BaseModel):
    funnel: list[FunnelStage]
    rejected_count: int
    conversions: Conversions
    dwell: list[DwellStat]
    stale: list[StaleJob]


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _pct(n: int, d: int) -> int | None:
    return None if d == 0 else round(100 * n / d)


def compute_stats(conn) -> StatsResult:
    jobs = pipeline.build_pipeline(conn)
    ranks = [_RANK.get(j.state, 0) for j in jobs if j.state != "rejected"]

    def reached(state: str) -> int:
        return sum(1 for r in ranks if r >= _RANK[state])

    funnel = [FunnelStage(state=s, label=_LABELS[s], count=reached(s)) for s in _FUNNEL_ORDER]
    rejected_count = sum(1 for j in jobs if j.state == "rejected")
    conversions = Conversions(
        applied_to_interview=_pct(reached("interviewing"), reached("applied")),
        interview_to_offer=_pct(reached("offer"), reached("interviewing")),
        interested_to_offer=_pct(reached("offer"), reached("interested")),
    )

    # 停留：依 code 分組事件時間軸，每段 = 下一事件 − 本事件（現階段 = now − 本事件）
    now = datetime.now()
    by_code: dict[str, list] = {}
    for e in store.load_state_events(conn):
        by_code.setdefault(e.code, []).append(e)
    samples: dict[str, list[int]] = {s: [] for s in _DWELL_STATES}
    for evs in by_code.values():
        for i, e in enumerate(evs):
            start = _parse(e.at)
            if start is None:
                continue
            end = _parse(evs[i + 1].at) if i + 1 < len(evs) else now
            if end is None:
                continue
            days = (end - start).days
            if e.state in samples and days >= 0:
                samples[e.state].append(days)
    dwell = [
        DwellStat(
            state=s, label=_LABELS[s],
            median_days=(int(median(samples[s])) if samples[s] else None),
            sample=len(samples[s]),
        )
        for s in _DWELL_STATES
    ]

    # 停滯：非終端、距 updated_at > STALE_DAYS
    stale: list[StaleJob] = []
    for t in store.load_tracked_jobs(conn):
        if t.state in pipeline.TERMINAL:
            continue
        upd = _parse(t.updated_at)
        if upd is None:
            continue
        days = (now - upd).days
        if days > STALE_DAYS:
            stale.append(StaleJob(
                code=t.code, company=t.company, title=t.title, state=t.state,
                label=_LABELS.get(t.state, t.state), days_since_update=days, url=t.url,
            ))
    stale.sort(key=lambda j: j.days_since_update, reverse=True)

    return StatsResult(funnel=funnel, rejected_count=rejected_count,
                       conversions=conversions, dwell=dwell, stale=stale)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_stats.py -q`
Expected: 5 個測試通過。

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/stats.py tests/test_stats.py
git commit -m "feat(sentinel): stats.compute_stats 聚合（漏斗/轉換率/停留/停滯）"
```

---

### Task 3: API 端點 + 前端 api 型別

**Files:**
- Modify: `src/career_sentinel/web/routers/dashboard.py`（加 `GET /api/stats`）
- Modify: `web/frontend/src/api.ts`（`StatsResp` 型別 + `getStats()`）
- Test: `tests/test_web_stats.py`

**Interfaces:**
- Consumes: `stats.compute_stats`、`deps.get_db_path`、`store.connect`。
- Produces: `GET /api/stats` 回 `StatsResult.model_dump()`；前端 `getStats(): Promise<StatsResp>`。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_web_stats.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel import store
from career_sentinel.web.app import create_app


def test_stats_endpoint_shape(tmp_path):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    store.merge_tracked_job(conn, "a", state="interested", company="甲", title="後端")
    store.set_tracked_state(conn, "b", "offer")
    c = TestClient(create_app(db_path=db))
    r = c.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert {"funnel", "rejected_count", "conversions", "dwell", "stale"} <= set(body)
    assert body["funnel"][0]["state"] == "interested"
    assert isinstance(body["conversions"]["interested_to_offer"], int)


def test_stats_endpoint_empty(tmp_path):
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    c = TestClient(create_app(db_path=db))
    r = c.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["rejected_count"] == 0 and body["stale"] == []
    assert body["conversions"]["applied_to_interview"] is None
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_stats.py -q`
Expected: FAIL（404 或 KeyError）

- [ ] **Step 3: 加端點**

在 `src/career_sentinel/web/routers/dashboard.py`：檔頭 `from ... import ...` 把 `stats` 加入（與既有 `store` 等同一行或新增一行 `from ... import stats`）。在既有某個 endpoint 之後加入：

```python
@router.get("/api/stats")
def stats_ep(db_path: str = Depends(get_db_path)) -> dict:
    return stats.compute_stats(store.connect(db_path)).model_dump()
```

- [ ] **Step 4: 加前端 api 型別與呼叫**

在 `web/frontend/src/api.ts` 加入（型別區塊末、`getStats` 放 GET 函式群附近）：

```typescript
export interface FunnelStage { state: string; label: string; count: number }
export interface Conversions {
  applied_to_interview: number | null;
  interview_to_offer: number | null;
  interested_to_offer: number | null;
}
export interface DwellStat { state: string; label: string; median_days: number | null; sample: number }
export interface StaleJob {
  code: string; company: string; title: string; state: string;
  label: string; days_since_update: number; url: string;
}
export interface StatsResp {
  funnel: FunnelStage[];
  rejected_count: number;
  conversions: Conversions;
  dwell: DwellStat[];
  stale: StaleJob[];
}

export async function getStats(): Promise<StatsResp> {
  const r = await fetch("/api/stats");
  return r.json();
}
```

- [ ] **Step 5: 跑測試確認通過（含全套）**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠 + 2 個新端點測試通過。

- [ ] **Step 6: 前端建置確認型別無誤**

Run: `cd web/frontend && npm run build`
Expected: build 成功。

- [ ] **Step 7: Commit**

```bash
git add src/career_sentinel/web/routers/dashboard.py web/frontend/src/api.ts tests/test_web_stats.py
git commit -m "feat(sentinel): /api/stats 端點 + 前端 api 型別"
```

---

### Task 4: 前端「求職統計」頁

**Files:**
- Create: `web/frontend/src/StatsPage.tsx`
- Modify: `web/frontend/src/Sidebar.tsx`（`PageKey` += `"stats"`、NAV 加項）
- Modify: `web/frontend/src/App.tsx`（掛載 `StatsPage`）

**Interfaces:**
- Consumes: `getStats`、`StatsResp` 等型別（Task 3）。

- [ ] **Step 1: 建立 `StatsPage.tsx`**

建立 `web/frontend/src/StatsPage.tsx`：

```tsx
import { Alert, Box, Group, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { getStats, type StatsResp } from "./api";

function Bar({ label, value, max, suffix }: { label: string; value: number; max: number; suffix?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <Group gap="sm" wrap="nowrap" align="center">
      <Text size="xs" w={84} style={{ flexShrink: 0 }} ta="right" c="dimmed">{label}</Text>
      <Box style={{ flex: 1, background: "var(--mantine-color-dark-6)", borderRadius: 6, overflow: "hidden" }}>
        <Box style={{ width: `${Math.max(pct, value > 0 ? 6 : 0)}%`, background: "var(--mantine-color-teal-7)",
          height: 22, borderRadius: 6, transition: "width 300ms" }} />
      </Box>
      <Text size="xs" w={64} ff="monospace" style={{ flexShrink: 0 }}>{value}{suffix ?? ""}</Text>
    </Group>
  );
}

function Pct({ title, v }: { title: string; v: number | null }) {
  return (
    <Paper bg="dark.6" radius="md" p="md" style={{ flex: 1 }}>
      <Text size="xs" c="dimmed">{title}</Text>
      <Text fw={700} size="xl" c="teal.4" ff="'Space Grotesk', sans-serif">
        {v === null ? "—" : `${v}%`}
      </Text>
    </Paper>
  );
}

export default function StatsPage() {
  const { data, isLoading, isError } = useQuery<StatsResp>({ queryKey: ["stats"], queryFn: getStats });

  if (isLoading) return <Box p={32}><Loader /></Box>;
  if (isError || !data) return <Box p={32}><Alert color="red">統計載入失敗，請重試。</Alert></Box>;

  const funnelMax = data.funnel.reduce((m, f) => Math.max(m, f.count), 0);
  const dwellMax = data.dwell.reduce((m, d) => Math.max(m, d.median_days ?? 0), 0);
  const hasData = funnelMax > 0 || data.rejected_count > 0;

  return (
    <Box mx="auto" px={24} py={32} style={{ maxWidth: 900 }}>
      <Title order={3} mb="lg" style={{ letterSpacing: "-0.3px" }}>求職統計</Title>

      {!hasData && <Text c="dimmed" size="sm">目前管道還沒有職缺——追蹤幾個職缺後，這裡會出現你的求職漏斗與進度。</Text>}

      {hasData && (
        <Stack gap="xl">
          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} size="sm" mb="md">漏斗（累積達到）</Text>
            <Stack gap={8}>
              {data.funnel.map((f) => <Bar key={f.state} label={f.label} value={f.count} max={funnelMax} />)}
            </Stack>
            {data.rejected_count > 0 && (
              <Text size="xs" c="dimmed" mt="sm">未錄取 {data.rejected_count} 筆（不計入漏斗）</Text>
            )}
          </Paper>

          <div>
            <Text fw={600} size="sm" mb="xs">轉換率</Text>
            <Text size="xs" c="dimmed" mb="sm">仍在進行或已成功的職缺之階段轉換</Text>
            <Group gap="sm">
              <Pct title="投遞 → 面試" v={data.conversions.applied_to_interview} />
              <Pct title="面試 → offer" v={data.conversions.interview_to_offer} />
              <Pct title="有興趣 → offer" v={data.conversions.interested_to_offer} />
            </Group>
          </div>

          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} size="sm" mb="md">各階段中位停留天數</Text>
            <Stack gap={8}>
              {data.dwell.map((d) => (
                d.sample > 0
                  ? <Bar key={d.state} label={d.label} value={d.median_days ?? 0} max={dwellMax} suffix=" 天" />
                  : <Group key={d.state} gap="sm"><Text size="xs" w={84} ta="right" c="dimmed">{d.label}</Text>
                      <Text size="xs" c="dimmed">尚無資料</Text></Group>
              ))}
            </Stack>
          </Paper>

          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} size="sm" mb="md">停滯提醒（超過 14 天未更新）</Text>
            {data.stale.length === 0
              ? <Text size="xs" c="dimmed">沒有停滯的職缺，保持得不錯 👍</Text>
              : <Stack gap={8}>
                  {data.stale.map((j) => (
                    <Group key={j.code} justify="space-between" wrap="nowrap">
                      <Text size="sm" truncate>{j.company || "（公司未知）"} · {j.title || j.code}
                        <Text span c="dimmed" size="xs"> · {j.label}</Text></Text>
                      <Group gap="sm" wrap="nowrap" style={{ flexShrink: 0 }}>
                        <Text size="xs" c="tangerine.5" ff="monospace">{j.days_since_update} 天</Text>
                        {j.url && <Text component="a" href={j.url} target="_blank" size="xs" c="dimmed">去 104 看</Text>}
                      </Group>
                    </Group>
                  ))}
                </Stack>}
          </Paper>
        </Stack>
      )}
    </Box>
  );
}
```

- [ ] **Step 2: Sidebar 加 nav 項與 PageKey**

在 `web/frontend/src/Sidebar.tsx`：
- import 加 `IconChartBar`：把 `IconChartBar` 併入 `@tabler/icons-react` 的 import 清單。
- `PageKey` 型別加 `"stats"`：`export type PageKey = "dashboard" | "stats" | "resume" | "jobs" | "chat" | "about";`
- `NAV` 陣列在 `dashboard` 之後插入一項：

```tsx
  { key: "stats", label: "求職統計", icon: IconChartBar },
```

- [ ] **Step 3: App.tsx 掛載 StatsPage**

在 `web/frontend/src/App.tsx`：
- import 加 `import StatsPage from "./StatsPage";`
- 在 Dashboard 的 `<div>` 之後加一行：

```tsx
        <div style={{ display: page === "stats" ? undefined : "none" }}><StatsPage /></div>
```

- [ ] **Step 4: 前端建置**

Run: `cd web/frontend && npm run build`
Expected: build 成功、無型別錯誤。

- [ ] **Step 5: Commit**

```bash
git add web/frontend/src/StatsPage.tsx web/frontend/src/Sidebar.tsx web/frontend/src/App.tsx
git commit -m "feat(sentinel): 求職統計頁（漏斗/轉換率/停留/停滯）"
```

---

## Self-Review

**1. Spec coverage：** spec 的四大區塊全覆蓋 — 狀態事件 log + backfill（Task 1）、漏斗/轉換率/停留/停滯聚合（Task 2，含 rejected 排除、reached 定義、分母 0→None、中位停留、停滯門檻與終端排除）、`/api/stats` 掛 dashboard router + 前端型別（Task 3）、統計頁 + 側欄 nav（Task 4）。非目標（不做 applied/interviewing 停留、不引圖表套件、不改既有頁）均遵守。

**2. Placeholder scan：** 無 TBD/TODO；每個程式步驟含完整程式碼；測試含實際斷言與預期輸出。

**3. Type/名稱一致性：** `StateEvent(code,state,at)`、`append_state_event`/`load_state_events`/`_backfill_state_events`、`compute_stats -> StatsResult`、欄位 `funnel/rejected_count/conversions/dwell/stale`、`FunnelStage/Conversions/DwellStat/StaleJob`、`getStats/StatsResp` 在後端定義與前端型別、測試、端點間一致；`_RANK` offer=6 與 reached 語意一致；`STALE_DAYS=14` 常數單一來源；`PageKey` 加 `"stats"` 與 NAV/App 掛載鍵一致。
