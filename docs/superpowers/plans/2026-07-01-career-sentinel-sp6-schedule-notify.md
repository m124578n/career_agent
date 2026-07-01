# career-sentinel SP6 定期檢視提醒 + 桌面通知 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** serve 開著時到 `notify_time` 提醒「該檢視求職動態」，發瀏覽器桌面通知 + 儀表板橫幅，使用者一鍵拉取；拉完若有新動態再發一則通知。

**Architecture:** serve 內起 daemon 背景執行緒，每 30s 用純函式 `should_prompt` 判斷到點與否、只設記憶體「提醒旗標」（不自己爬，因 headful 限制）。前端輪詢 `/api/schedule`，`due` 邊緣發桌面通知 + 橫幅；橫幅一鍵走既有 `/api/scrape`。scrape 完成後 `run_pipeline` 回傳本次 diff 新增計數，runner 存入狀態、`/api/status` 回傳，前端據以發第二則通知。

**Tech Stack:** Python 3.12 / Pydantic v2 / FastAPI / threading（daemon 排程執行緒）/ React 18 + Vite + Mantine 7 + TanStack Query / Web Notification API。

## Global Constraints

- 排程器**只設提醒旗標、不自己爬**（爬 104 需 headful Chrome 過 Cloudflare，無人值守不可靠）。
- 排程狀態**純記憶體**（serve 生命週期內），不寫 DB。後端只綁 127.0.0.1。
- 一鍵拉取**只拉職動態**（重用既有 `POST /api/scrape`）；推薦分開（橫幅次連結跳推薦分頁，走 SP5 既有流程）。不破壞 SP5 的 recommend stateless。
- 桌面通知用 **Web Notification API**；未授權/被拒 → 靜默 fallback（只橫幅與既有標記，不報錯、不阻斷）。
- 到點語意：`should_prompt` 用 `now 的 HH:MM >= notify_time` 且「今天尚未提醒」（`last_prompted_date != 今天`）；`notify_time` 為 None → 永不 due；每天最多提醒一次。
- **啟動已過點不補觸發**：`scheduler.start` 時若 `should_prompt(now, notify_time, None)` 為真，就把 `last_prompted_date` 預設為今天（當天不再跳、隔天正常）。
- 既有 115 測試不得回歸。前端須 `npm run build` 通過。
- pytest / npm 從對應目錄執行：後端 `cd sentinel && uv run pytest`；前端 `cd sentinel/web/frontend && npm run build`。

---

### Task 1: `ChangeCounts` model

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（新增 `ChangeCounts`）
- Test: `sentinel/tests/test_models.py`

**Interfaces:**
- Consumes: 既有 `Diff`（`new_viewers`/`status_changes`/`new_messages`/`new_invites` 四個 list）。
- Produces: `ChangeCounts(new_viewers:int=0, status_changes:int=0, new_messages:int=0, new_invites:int=0)`，`total` property（四者加總），`from_diff(d: Diff) -> ChangeCounts` classmethod。供 Task 2 使用。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_models.py` 末尾加：

```python
def test_change_counts_total():
    from career_sentinel.models import ChangeCounts
    c = ChangeCounts(new_viewers=2, status_changes=1, new_messages=3, new_invites=1)
    assert c.total == 7

def test_change_counts_defaults_zero():
    from career_sentinel.models import ChangeCounts
    assert ChangeCounts().total == 0

def test_change_counts_from_diff():
    from career_sentinel.models import (
        Application, ChangeCounts, Diff, Message, StatusChange, Viewer,
    )
    d = Diff(
        new_viewers=[Viewer(company="A", job_title="x", viewed_at="t")],
        status_changes=[StatusChange(
            application=Application(job_id="1", company="B", title="t", status="已讀", applied_at="d"),
            old_status="已送出", new_status="已讀")],
        new_messages=[Message(thread_id="m1", company="C", last_message="hi")],
        new_invites=[Message(thread_id="m1", company="C", last_message="hi", has_interview_invite=True)],
    )
    c = ChangeCounts.from_diff(d)
    assert (c.new_viewers, c.status_changes, c.new_messages, c.new_invites) == (1, 1, 1, 1)
    assert c.total == 4
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_models.py -q`
Expected: FAIL（ImportError: cannot import name 'ChangeCounts'）

- [ ] **Step 3: 新增 model**

在 `models.py` 末尾加（`Diff` 已定義於本檔前面，直接引用型別）：

```python
class ChangeCounts(BaseModel):
    new_viewers: int = 0
    status_changes: int = 0
    new_messages: int = 0
    new_invites: int = 0

    @property
    def total(self) -> int:
        return self.new_viewers + self.status_changes + self.new_messages + self.new_invites

    @classmethod
    def from_diff(cls, d: "Diff") -> "ChangeCounts":
        return cls(
            new_viewers=len(d.new_viewers),
            status_changes=len(d.status_changes),
            new_messages=len(d.new_messages),
            new_invites=len(d.new_invites),
        )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_models.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/models.py tests/test_models.py
git commit -m "feat(sentinel): ChangeCounts model（SP6）"
```

---

### Task 2: `run_pipeline` 回傳計數 + runner 存/回 `last_change_counts`

**Files:**
- Modify: `sentinel/src/career_sentinel/cli.py`（`run_pipeline` 回 tuple；`_cmd_run` 解構）
- Modify: `sentinel/src/career_sentinel/web/runner.py`（`_State` 加欄位、`default_scrape` 設狀態、`status()` 回傳）
- Test: `sentinel/tests/test_web_runner.py`（`_reset` 加欄位、新增計數測試）

**Interfaces:**
- Consumes: `ChangeCounts`（Task 1）、既有 `diff.diff_against_last`、`digest.summarize`。
- Produces: `run_pipeline(...) -> tuple[str, ChangeCounts]`；`runner.status()` 回 dict 多一鍵 `last_change_counts: dict`（`ChangeCounts.model_dump()`）；`default_scrape` 仍回 `set[str]`（failed），但副作用設 `_state.last_change_counts`。供 Task 4（status API）與前端使用。

- [ ] **Step 1: 寫失敗測試（runner 存計數）**

在 `sentinel/tests/test_web_runner.py`：先更新 `_reset()` 加一行 `runner._state.last_change_counts = __import__("career_sentinel.models", fromlist=["ChangeCounts"]).ChangeCounts()`（或在檔頂 import `from career_sentinel.models import ChangeCounts` 後寫 `runner._state.last_change_counts = ChangeCounts()`）。然後末尾加：

```python
def test_default_scrape_records_change_counts(tmp_path, monkeypatch):
    from career_sentinel import store
    from career_sentinel.models import Snapshot, Viewer
    from career_sentinel.scraper import real
    _reset()
    db = str(tmp_path / "db.sqlite")
    # 第一次：一個 viewer（相對空前次 → 新增 1）
    snap1 = Snapshot(viewers=[Viewer(company="A", job_title="x", viewed_at="t")])
    monkeypatch.setattr(real, "scrape_session", lambda: (snap1, set()))
    runner.default_scrape(db)
    assert runner.status()["last_change_counts"]["new_viewers"] == 1
    # 第二次：同一 viewer（無新增 → 0）
    monkeypatch.setattr(real, "scrape_session", lambda: (snap1, set()))
    runner.default_scrape(db)
    assert runner.status()["last_change_counts"]["new_viewers"] == 0

def test_status_has_change_counts_key():
    _reset()
    assert "last_change_counts" in runner.status()
    assert runner.status()["last_change_counts"]["new_viewers"] == 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_runner.py -q`
Expected: FAIL（`last_change_counts` KeyError / `_state` 無此欄位）

- [ ] **Step 3: 改 `cli.run_pipeline` 回 tuple**

`cli.py` 頂部 import 加 `ChangeCounts`：把 `from .models import Snapshot` 改為 `from .models import ChangeCounts, Snapshot`。
`run_pipeline` 改為（保留既有邏輯，末尾回 tuple）：

```python
def run_pipeline(scrape: Callable[[], tuple[Snapshot, set[str]]], conn, *, now: str) -> tuple[str, ChangeCounts]:
    snapshot, failed = scrape()
    if failed:
        snapshot = _carry_forward(conn, snapshot, failed)
    sid = store.save_snapshot(conn, snapshot, run_at=now)
    d = diff.diff_against_last(conn, sid)
    report = digest.summarize(d, snapshot)
    if failed:
        report += "\n\n⚠️ 本次未讀到：" + "、".join(sorted(failed)) + "（沿用上次）"
    return report, ChangeCounts.from_diff(d)
```

`_cmd_run` 的呼叫（約第 71 行）改為解構：

```python
    report, _ = run_pipeline(
        lambda: result,
        conn,
        now=datetime.now().isoformat(timespec="seconds"),
    )
    print(report)
```

- [ ] **Step 4: 改 `runner`**

`runner.py`：頂部加 `from ..models import ChangeCounts`。`_State` dataclass 加欄位：

```python
@dataclass
class _State:
    running: bool = False
    last_run: str | None = None
    last_error: str | None = None
    last_failed_readers: list[str] = field(default_factory=list)
    last_change_counts: ChangeCounts = field(default_factory=ChangeCounts)
```

`status()` 回傳加一鍵：

```python
def status() -> dict:
    return {
        "running": _state.running,
        "last_run": _state.last_run,
        "last_error": _state.last_error,
        "last_failed_readers": list(_state.last_failed_readers),
        "last_change_counts": _state.last_change_counts.model_dump(),
    }
```

`default_scrape` 內解構 run_pipeline 並設狀態：

```python
def default_scrape(db_path: str | None = None) -> set[str]:
    """真實抓取：scrape_session → run_pipeline 存。未登入 raise LoginRequired。需真瀏覽器。"""
    from .. import cli, config, store
    from ..scraper import real

    result = real.scrape_session()
    if result is None:
        raise LoginRequired()
    failed = result[1]
    conn = store.connect(db_path or config.db_path())
    try:
        _report, counts = cli.run_pipeline(lambda: result, conn, now=datetime.now().isoformat(timespec="seconds"))
        _state.last_change_counts = counts
    finally:
        conn.close()
    return failed
```

- [ ] **Step 5: 跑測試確認通過 + 全測試無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠；含既有 runner 測試與新增 2 個）

- [ ] **Step 6: Commit**

```bash
cd sentinel && git add src/career_sentinel/cli.py src/career_sentinel/web/runner.py tests/test_web_runner.py
git commit -m "feat(sentinel): run_pipeline 回本次新增計數，runner 記錄 last_change_counts（SP6）"
```

---

### Task 3: `web/scheduler.py` — 到點判斷 + 背景執行緒 + 記憶體狀態

**Files:**
- Create: `sentinel/src/career_sentinel/web/scheduler.py`
- Test: `sentinel/tests/test_scheduler.py`

**Interfaces:**
- Consumes: 既有 `Settings`（`notify_time: str | None`）。
- Produces: `should_prompt(now: datetime, notify_time: str | None, last_prompted_date: str | None) -> bool`（純）、`initial_prompted_date(now: datetime, notify_time: str | None) -> str | None`（純，啟動已過點回今天否則 None）、`start(load_settings: Callable[[], Settings]) -> None`（起 daemon thread，有 guard 防重複）、`state() -> dict`（`{due, notify_time, last_prompted_date}`）、`ack() -> None`（清 due）、`_reset_for_test() -> None`（測試用，清狀態與 started 旗標）。

- [ ] **Step 1: 寫失敗測試（純函式）**

Create `sentinel/tests/test_scheduler.py`：

```python
from datetime import datetime

from career_sentinel.web import scheduler


def _at(hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(2026, 7, 1, int(h), int(m))


def test_should_prompt_at_time_not_yet_prompted():
    assert scheduler.should_prompt(_at("12:00"), "12:00", None) is True

def test_should_prompt_after_time():
    assert scheduler.should_prompt(_at("13:30"), "12:00", None) is True

def test_should_prompt_before_time():
    assert scheduler.should_prompt(_at("11:00"), "12:00", None) is False

def test_should_prompt_already_prompted_today():
    assert scheduler.should_prompt(_at("12:00"), "12:00", "2026-07-01") is False

def test_should_prompt_prompted_yesterday_reprompts():
    assert scheduler.should_prompt(_at("12:00"), "12:00", "2026-06-30") is True

def test_should_prompt_no_notify_time():
    assert scheduler.should_prompt(_at("12:00"), None, None) is False

def test_initial_prompted_date_past_marks_today():
    assert scheduler.initial_prompted_date(_at("13:00"), "12:00") == "2026-07-01"

def test_initial_prompted_date_before_returns_none():
    assert scheduler.initial_prompted_date(_at("11:00"), "12:00") is None

def test_initial_prompted_date_no_time_returns_none():
    assert scheduler.initial_prompted_date(_at("13:00"), None) is None


def test_ack_clears_due():
    scheduler._reset_for_test()
    scheduler._state.due = True
    scheduler.ack()
    assert scheduler.state()["due"] is False

def test_state_shape():
    scheduler._reset_for_test()
    s = scheduler.state()
    assert set(s.keys()) == {"due", "notify_time", "last_prompted_date"}
    assert s["due"] is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_scheduler.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.web.scheduler）

- [ ] **Step 3: 實作 `scheduler.py`**

Create `sentinel/src/career_sentinel/web/scheduler.py`：

```python
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..models import Settings


@dataclass
class _State:
    due: bool = False
    notify_time: str | None = None
    last_prompted_date: str | None = None
    started: bool = False


_state = _State()
_lock = threading.Lock()


def should_prompt(now: datetime, notify_time: str | None, last_prompted_date: str | None) -> bool:
    """到點（HH:MM >= notify_time）且今天尚未提醒 → True。notify_time None → False。"""
    if not notify_time:
        return False
    if last_prompted_date == now.date().isoformat():
        return False
    return now.strftime("%H:%M") >= notify_time


def initial_prompted_date(now: datetime, notify_time: str | None) -> str | None:
    """啟動當下若已過點（會立即觸發）→ 回今天（避免啟動即跳）；否則 None。"""
    if should_prompt(now, notify_time, None):
        return now.date().isoformat()
    return None


def _loop(load_settings: Callable[[], Settings]) -> None:
    while True:
        try:
            nt = load_settings().notify_time
            now = datetime.now()
            with _lock:
                _state.notify_time = nt
                if should_prompt(now, nt, _state.last_prompted_date):
                    _state.due = True
                    _state.last_prompted_date = now.date().isoformat()
        except Exception:  # noqa: BLE001 - 背景執行緒任何錯都不崩
            pass
        time.sleep(30)


def start(load_settings: Callable[[], Settings]) -> None:
    """起 daemon 背景執行緒（有 guard，多次呼叫只起一條）。啟動已過點不補觸發。"""
    with _lock:
        if _state.started:
            return
        _state.started = True
        try:
            now = datetime.now()
            nt = load_settings().notify_time
            _state.notify_time = nt
            _state.last_prompted_date = initial_prompted_date(now, nt)
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_loop, args=(load_settings,), daemon=True).start()


def state() -> dict:
    with _lock:
        return {
            "due": _state.due,
            "notify_time": _state.notify_time,
            "last_prompted_date": _state.last_prompted_date,
        }


def ack() -> None:
    with _lock:
        _state.due = False


def _reset_for_test() -> None:
    with _lock:
        _state.due = False
        _state.notify_time = None
        _state.last_prompted_date = None
        _state.started = False
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_scheduler.py -q`
Expected: PASS（11 passed）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/web/scheduler.py tests/test_scheduler.py
git commit -m "feat(sentinel): 排程器 scheduler（到點判斷純函式 + daemon 執行緒 + 記憶體狀態）（SP6）"
```

---

### Task 4: `/api/schedule` API + serve 啟動排程器

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`（新增 2 路由 + create_app 啟動 scheduler）
- Test: `sentinel/tests/test_web_schedule.py`

**Interfaces:**
- Consumes: `scheduler.state`/`ack`/`start`（Task 3）、既有 `store.load_settings`、`runner.status`（Task 2 已含 `last_change_counts`）。
- Produces: `GET /api/schedule` → `scheduler.state()`；`POST /api/schedule/ack` → `{"due": False}`；`create_app` 啟動時呼叫 `scheduler.start(...)`。

- [ ] **Step 1: 寫失敗測試**

Create `sentinel/tests/test_web_schedule.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel.web import scheduler
from career_sentinel.web.app import create_app


def _client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def test_schedule_default_not_due(tmp_path):
    scheduler._reset_for_test()
    r = _client(tmp_path).get("/api/schedule")
    assert r.status_code == 200
    body = r.json()
    assert body["due"] is False
    assert set(body.keys()) == {"due", "notify_time", "last_prompted_date"}


def test_schedule_ack_clears_due(tmp_path):
    scheduler._reset_for_test()
    client = _client(tmp_path)
    scheduler._state.due = True
    assert client.get("/api/schedule").json()["due"] is True
    r = client.post("/api/schedule/ack")
    assert r.status_code == 200
    assert r.json()["due"] is False
    assert client.get("/api/schedule").json()["due"] is False


def test_status_exposes_change_counts(tmp_path):
    scheduler._reset_for_test()
    r = _client(tmp_path).get("/api/status")
    assert r.status_code == 200
    assert "last_change_counts" in r.json()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_schedule.py -q`
Expected: FAIL（/api/schedule 404）

- [ ] **Step 3: 加路由 + 啟動排程器**

`web/app.py`：頂部 import 加 `scheduler`——把 `from . import runner` 改為 `from . import runner, scheduler`。

在 `create_app` 內、`resolved_db` 定義之後、`_conn` 定義之後，加啟動（放在 return 前任何位置皆可，建議緊接 `_conn` 定義後）：

```python
    scheduler.start(lambda: store.load_settings(_conn()))
```

在 `GET /api/status` 路由之後加兩個路由：

```python
    @app.get("/api/schedule")
    def schedule() -> dict:
        return scheduler.state()

    @app.post("/api/schedule/ack")
    def schedule_ack() -> dict:
        scheduler.ack()
        return {"due": False}
```

- [ ] **Step 4: 跑測試確認通過 + 全測試無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/web/app.py tests/test_web_schedule.py
git commit -m "feat(sentinel): GET /api/schedule + ack + serve 啟動排程器（SP6）"
```

---

### Task 5: 前端基礎 — `api.ts` 排程型別 + `notify.ts` 桌面通知

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`
- Create: `sentinel/web/frontend/src/notify.ts`

**Interfaces:**
- Produces: `ScheduleState`、`getSchedule()`、`ackSchedule()`、`StatusResp.last_change_counts`；`ensurePermission()`、`notify(title, body)`。供 Task 6 使用。

- [ ] **Step 1: api.ts 加型別與函式**

在 `sentinel/web/frontend/src/api.ts`：把既有 `StatusResp` 介面改為多一欄位（其餘不動）：

```typescript
export interface ChangeCounts { new_viewers: number; status_changes: number; new_messages: number; new_invites: number }
export interface StatusResp { running: boolean; last_run: string | null; last_error: string | null; last_failed_readers: string[]; last_change_counts: ChangeCounts }
```

在檔案末尾加：

```typescript
export interface ScheduleState { due: boolean; notify_time: string | null; last_prompted_date: string | null }

export async function getSchedule(): Promise<ScheduleState> {
  const r = await fetch("/api/schedule");
  return r.json();
}

export async function ackSchedule(): Promise<void> {
  await fetch("/api/schedule/ack", { method: "POST" });
}
```

- [ ] **Step 2: 建 notify.ts**

Create `sentinel/web/frontend/src/notify.ts`：

```typescript
// 瀏覽器桌面通知薄封裝。未授權/不支援 → 靜默 no-op（fallback 靠儀表板橫幅）。
export async function ensurePermission(): Promise<void> {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    try {
      await Notification.requestPermission();
    } catch {
      // 忽略：某些瀏覽器在非使用者手勢下會 reject
    }
  }
}

export function notify(title: string, body: string): void {
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  try {
    new Notification(title, { body });
  } catch {
    // 忽略通知建構失敗
  }
}
```

- [ ] **Step 3: build 確認通過**

Run: `cd sentinel/web/frontend && npm run build`
Expected: build 成功、無 TS 錯誤

- [ ] **Step 4: Commit**

```bash
cd sentinel && git add web/frontend/src/api.ts web/frontend/src/notify.ts
git commit -m "feat(sentinel): 前端排程 api + 桌面通知封裝 notify.ts（SP6）"
```

---

### Task 6: 前端整合 — controlled tab + 儀表板橫幅 + 兩則通知

**Files:**
- Modify: `sentinel/web/frontend/src/App.tsx`（Tabs 改 controlled，傳 `onGoRecommend` 給 Dashboard）
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`（排程輪詢 + 橫幅 + due 邊緣通知 + scrape 完成邊緣通知）

**Interfaces:**
- Consumes: `getSchedule`/`ackSchedule`/`ScheduleState`（Task 5）、`ensurePermission`/`notify`（Task 5）、`StatusResp.last_change_counts`（Task 5）、既有 `startScrape`/`getStatus`/`getSnapshot`。

- [ ] **Step 1: App.tsx 改 controlled tab**

覆寫 `sentinel/web/frontend/src/App.tsx`：

```tsx
import { Tabs } from "@mantine/core";
import { useState } from "react";
import Dashboard from "./Dashboard";
import MatchPage from "./MatchPage";
import RecommendPage from "./RecommendPage";
import ResumePage from "./ResumePage";

export default function App() {
  const [tab, setTab] = useState<string | null>("dashboard");
  return (
    <Tabs value={tab} onChange={setTab} keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
        <Tabs.Tab value="match">JD 比對</Tabs.Tab>
        <Tabs.Tab value="recommend">推薦</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard onGoRecommend={() => setTab("recommend")} /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
      <Tabs.Panel value="match"><MatchPage /></Tabs.Panel>
      <Tabs.Panel value="recommend"><RecommendPage /></Tabs.Panel>
    </Tabs>
  );
}
```

- [ ] **Step 2: Dashboard.tsx 加排程輪詢 + 橫幅 + 兩則通知**

覆寫 `sentinel/web/frontend/src/Dashboard.tsx`（在既有基礎上加：`onGoRecommend` prop、排程 query、`ensurePermission` 掛載、due 邊緣通知+橫幅、scrape 完成邊緣讀 `last_change_counts` 發通知）：

```tsx
import { Alert, Badge, Button, Card, Container, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ackSchedule, getSchedule, getSnapshot, getStatus, startScrape } from "./api";
import { ensurePermission, notify } from "./notify";
import SettingsModal from "./SettingsModal";

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card withBorder padding="md" radius="md" style={{ flex: 1, minWidth: 280 }}>
      <Title order={4} mb="sm">{title}（{count}）</Title>
      <Stack gap={8}>{children}</Stack>
    </Card>
  );
}

export default function Dashboard({ onGoRecommend }: { onGoRecommend: () => void }) {
  const qc = useQueryClient();
  const [polling, setPolling] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const prevDue = useRef(false);

  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({
    queryKey: ["status"],
    queryFn: getStatus,
    refetchInterval: polling ? 2000 : false,
  });
  const schedule = useQuery({ queryKey: ["schedule"], queryFn: getSchedule, refetchInterval: 30000 });

  useEffect(() => { ensurePermission(); }, []);

  // 到點：due 由 false→true 的邊緣 → 桌面通知（橫幅由 schedule.data.due 直接驅動）
  useEffect(() => {
    const due = schedule.data?.due ?? false;
    if (due && !prevDue.current) {
      notify("⏰ career-sentinel", "該檢視求職動態了，點「立即拉取」更新。");
    }
    prevDue.current = due;
  }, [schedule.data?.due]);

  // scrape 完成：running 由 true→false 的邊緣 → 讀本次新增計數發通知
  useEffect(() => {
    if (polling && status.data && !status.data.running) {
      setPolling(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
      const c = status.data.last_change_counts;
      const total = c ? c.new_viewers + c.status_changes + c.new_messages + c.new_invites : 0;
      if (total > 0) notify("🔔 career-sentinel", `發現 ${total} 筆新動態（看過我／訊息／狀態變化）。`);
    }
  }, [polling, status.data?.running, status.data, qc]);

  async function refresh() {
    const r = await startScrape();
    if (r.status !== "already_running") { /* 開始新的一輪 */ }
    setPolling(true);
  }

  async function onBannerPull() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
    await refresh();
  }

  async function onBannerDismiss() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
  }

  const s = snap.data;
  const running = polling || status.data?.running;
  const due = schedule.data?.due ?? false;

  return (
    <Container size="lg" py="lg">
      <Group justify="space-between" mb="md">
        <Title order={2}>career-sentinel</Title>
        <Group>
          <Text size="sm" c="dimmed">上次更新：{s?.run_at ?? "—"}</Text>
          <Button variant="default" onClick={() => setSettingsOpen(true)}>設定</Button>
          <Button onClick={refresh} loading={running} disabled={running}>重新抓取</Button>
        </Group>
      </Group>

      {due && (
        <Alert color="yellow" mb="md" withCloseButton onClose={onBannerDismiss} title="⏰ 該檢視求職動態了">
          <Group>
            <Button size="xs" onClick={onBannerPull} loading={running} disabled={running}>立即拉取</Button>
            <Button size="xs" variant="light" onClick={onGoRecommend}>也拉推薦</Button>
          </Group>
        </Alert>
      )}

      {status.data?.last_error && (
        <Text c="red" mb="sm">⚠️ {status.data.last_error}</Text>
      )}
      {s && s.failed_readers.length > 0 && (
        <Text c="orange" mb="sm">⚠️ 本次未讀到：{s.failed_readers.join("、")}（沿用上次）</Text>
      )}

      <Card withBorder padding="md" radius="md" mb="md">
        <Title order={4} mb="xs">今日彙整</Title>
        <Text style={{ whiteSpace: "pre-wrap" }}>{s?.digest ?? "載入中…"}</Text>
      </Card>

      <Group align="flex-start" gap="md" wrap="wrap">
        <Panel title="誰看過我" count={s?.viewers.length ?? 0}>
          {s?.viewers.map((v, i) => (
            <Text key={i} size="sm">{v.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}{v.company}　<Text span c="dimmed">{v.job_title} · {v.viewed_at}</Text></Text>
          ))}
        </Panel>
        <Panel title="我的應徵" count={s?.applications.length ?? 0}>
          {s?.applications.map((a) => (
            <Text key={a.job_id} size="sm">{a.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}{a.company} · {a.title}　<Badge size="sm" variant="light">{a.status}</Badge></Text>
          ))}
        </Panel>
        <Panel title="訊息 · 面試" count={s?.messages.length ?? 0}>
          {s?.messages.map((m) => (
            <Text key={m.thread_id} size="sm">
              {m.has_interview_invite && <Badge size="sm" color="orange" mr={6}>面試</Badge>}
              {m.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}
              {m.company}：<Text span c="dimmed">{m.last_message}</Text>
            </Text>
          ))}
        </Panel>
      </Group>
      <SettingsModal opened={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </Container>
  );
}
```

註：`refresh()` 移除了原本 `already_running` 的特殊分支（無論如何都進入 polling 觀察，行為等價且更簡單）。橫幅用 Mantine `Alert`。

- [ ] **Step 3: build 確認通過**

Run: `cd sentinel/web/frontend && npm run build`
Expected: build 成功、無 TS 錯誤

- [ ] **Step 4: Commit**

```bash
cd sentinel && git add web/frontend/src/App.tsx web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 儀表板到點橫幅 + 桌面通知（到點/拉取完成）+ controlled tab（SP6）"
```

---

### Task 7: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: 真機端到端驗證**

```bash
cd sentinel && uv run career-sentinel serve
```
瀏覽器開儀表板 → 允許通知權限 → 到「設定」把通知時間改成**現在的一兩分鐘後**（HH:MM）→ 等 ≤30s 輪詢 → 應跳桌面通知「⏰ 該檢視求職動態了」+ 頂部黃色橫幅 → 按「立即拉取」→ headful Chrome 爬取 → 完成後若有新動態跳「🔔 發現 N 筆新動態」；按橫幅「也拉推薦」→ 切到推薦分頁。
（未授權通知時：只出現橫幅，功能不受阻。）

- [ ] **Step 2: 全測試最終確認**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 3: 更新 roadmap + ledger、commit**

`docs/superpowers/career-sentinel-roadmap.md`：把 SP6 表格列改為 `| ~~SP6~~ | ~~⏰ 定期檢視 + 通知排程~~ | ✅ 已完成（見上） | — |`，在「✅ 已完成」區加一條 SP6 摘要，並把 SP6 review 期發現的 minors（若有）記入技術債區。
`.superpowers/sdd/progress.md`：append SP6 各 Task 完成與真機驗證結果。

```bash
git add docs/superpowers/career-sentinel-roadmap.md .superpowers/sdd/progress.md
git commit -m "docs(sentinel): SP6 定期檢視提醒 + 桌面通知 完成（roadmap + ledger）"
```

---

## Self-Review

**1. Spec coverage：**
- 排程器 daemon 執行緒、只設旗標不爬 → Task 3（`start`/`_loop`）✅
- 到點判斷純函式（`should_prompt`）+ 啟動已過點不補觸發（`initial_prompted_date`）→ Task 3 ✅
- 排程狀態純記憶體、不寫 DB → Task 3（`_State`）✅
- `GET /api/schedule` + `POST /api/schedule/ack` → Task 4 ✅
- serve 啟動排程器 → Task 4（`create_app` 內 `scheduler.start`）✅
- scrape 完成回本次新增計數（`ChangeCounts`）+ `/api/status` 回傳 → Task 1（model）+ Task 2（run_pipeline/runner/status）✅
- 桌面通知（Web Notification）+ 未授權 fallback → Task 5（`notify.ts`）✅
- 到點通知 + 橫幅（立即拉取走既有 scrape、也拉推薦跳分頁、關閉 ack）→ Task 6 ✅
- 拉取完成通知「N 筆新動態」（total>0 才發）→ Task 6 ✅
- 一鍵只拉動態、推薦分開 → Task 6（橫幅主按鈕 scrape、次連結 onGoRecommend）✅
- 測試（should_prompt/initial/計數/API/build/真機）→ Tasks 1·2·3·4·6·7 ✅
- 非目標（自動爬/多時段/Email/推薦納一鍵/持久化）→ 未實作，符合 ✅

**2. Placeholder scan：** 無 TBD/TODO；每個 code step 均含完整程式碼。

**3. Type consistency：**
- `ChangeCounts`（Task 1）欄位 new_viewers/status_changes/new_messages/new_invites + total + from_diff，於 Task 2 用 `ChangeCounts.from_diff(d)` 與 `.model_dump()`、Task 5 TS `ChangeCounts` 介面、Task 6 加總一致。
- `run_pipeline -> tuple[str, ChangeCounts]`（Task 2）與兩個呼叫者（cli `_cmd_run` 解構 `report, _`；runner `default_scrape` 解構 `_report, counts`）一致。
- `scheduler` 的 `should_prompt`/`initial_prompted_date`/`start`/`state`/`ack`/`_reset_for_test`（Task 3）與 Task 4 API（`scheduler.state()`/`scheduler.ack()`/`scheduler.start(...)`）、測試呼叫一致。
- `ScheduleState`（due/notify_time/last_prompted_date）Task 5 TS 介面與 Task 3 `state()` 回傳鍵一致。
- Task 6 `Dashboard` 收 `onGoRecommend` prop 與同 Task 6 的 App.tsx（Step 1）傳入一致。

**開放問題解決紀錄：** 「啟動已過點語意」以 `initial_prompted_date` 實作並單測（Task 3）；「run_pipeline 取計數接點」確認為 `run_pipeline` 內既有 `d = diff.diff_against_last(...)`，以 `ChangeCounts.from_diff(d)` 回傳（Task 2）。
