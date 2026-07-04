# career-sentinel SP14：等待處可見進度流程 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 爬蟲背景管線顯示真階段 stepper（全域、切分頁可見），LLM/同步爬蟲等待處顯示 inline「進行中…（已 N 秒）」計時。

**Architecture:** 後端 `runner` 加 `phase` 狀態、`real.scrape` 透過 `on_phase` callback 逐階段回報，`status()` 輸出 phase。前端 `ScrapeStepper`（讀 `status.phase`、渲染六段 stepper、phase 不在清單即自我隱藏）掛在 App 內容頂部；`useElapsed` hook + `BusyHint` 元件套到各頁既有 busy 布林旁。

**Tech Stack:** Python 3.12（`sqlite3`/threading）、FastAPI；React 18 + Mantine 7（Cockpit 深色）+ TanStack Query + Vite；測試 pytest（`uv run pytest`）、前端 `npm run build`。

## Global Constraints

- **爬蟲 phase best-effort、絕不影響抓取**：`on_phase` 只寫字串；`on_phase=None` 時完全不呼叫；reader 失敗（既有 try/except）不影響後續 reader 的 phase 回報；`_run` 的 `finally` 一律清空 phase。
- **phase 值（後端回報字串）**：`establish` / `viewers` / `applications` / `messages` / `interviews` / `digest` / `""`(閒置)。**stepper 六段順序與中文標籤固定**：建立連線→誰看過我→應徵→訊息→面試→整理。
- **LLM 單次用計時、不假造步驟**；同步阻塞爬蟲（recommend/resume104/apply）走 inline 計時、不進全域 stepper。
- **不改既有行為/回傳**：新增參數皆有預設（`on_phase=None`、`phase` 預設 `""`），既有呼叫端不傳也不變。
- Cockpit 深色主題：小尺寸、次要色（`c="dimmed"`、`size="xs"`）。
- `.superpowers/sdd/progress.md` 是 gitignored——不要 git add。main push 觸發自動部署——需明講。

---

### Task 1：後端——爬蟲階段回報（runner + real.scrape）

**Files:**
- Modify: `sentinel/src/career_sentinel/web/runner.py`
- Modify: `sentinel/src/career_sentinel/scraper/real.py`
- Test: `sentinel/tests/test_scrape_phase.py`（新）

**Interfaces:**
- Produces:
  - `runner.set_phase(name: str) -> None`（上鎖寫 `_state.phase`）
  - `runner.status()` 回傳新增 `"phase": str`
  - `real.scrape(page, on_phase: Callable[[str], None] | None = None) -> tuple[Snapshot, set[str]]`
  - `real.scrape_session(on_phase=None) -> tuple[Snapshot, set[str]] | None`
- Consumes: 既有 `real.fetch_viewers/applications/messages/interviews`、`cli.run_pipeline`。

- [ ] **Step 1: 寫失敗測試**

Create `sentinel/tests/test_scrape_phase.py`：

```python
import pytest

from career_sentinel.scraper import real
from career_sentinel.web import runner


@pytest.fixture(autouse=True)
def _reset_runner_state():
    """runner._state 是模組全域；每測後還原，避免 last_error/phase 洩漏到其他測試。"""
    yield
    runner._state.phase = ""
    runner._state.last_error = None
    runner._state.last_run = None
    runner._state.last_failed_readers = []
    runner._state.running = False


def _stub_readers(monkeypatch):
    monkeypatch.setattr(real, "fetch_viewers", lambda p: [])
    monkeypatch.setattr(real, "fetch_applications", lambda p: [])
    monkeypatch.setattr(real, "fetch_messages", lambda p: [])
    monkeypatch.setattr(real, "fetch_interviews", lambda p: [])


def test_scrape_reports_phases_in_order(monkeypatch):
    _stub_readers(monkeypatch)
    seen = []
    snap, failed = real.scrape(object(), on_phase=seen.append)
    assert seen == ["viewers", "applications", "messages", "interviews"]
    assert failed == set()


def test_scrape_on_phase_none_does_not_crash(monkeypatch):
    _stub_readers(monkeypatch)
    snap, failed = real.scrape(object())  # on_phase 預設 None
    assert failed == set()


def test_scrape_reports_all_phases_even_when_reader_fails(monkeypatch):
    _stub_readers(monkeypatch)

    def boom(p):
        raise RuntimeError("reader down")

    monkeypatch.setattr(real, "fetch_viewers", boom)
    seen = []
    snap, failed = real.scrape(object(), on_phase=seen.append)
    # phase 在每個 reader 前回報，故失敗不影響後續回報
    assert seen == ["viewers", "applications", "messages", "interviews"]
    assert "viewers" in failed


def test_set_phase_reflected_in_status():
    runner.set_phase("viewers")
    assert runner.status()["phase"] == "viewers"
    runner.set_phase("")
    assert runner.status()["phase"] == ""


def test_run_clears_phase_on_success():
    runner.set_phase("digest")
    runner._run(lambda: set())
    assert runner.status()["phase"] == ""


def test_run_clears_phase_on_exception():
    runner.set_phase("viewers")

    def boom():
        raise RuntimeError("scrape failed")

    runner._run(boom)
    assert runner.status()["phase"] == ""
    assert runner.status()["last_error"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_scrape_phase.py -q`
Expected: FAIL（`real.scrape` 無 `on_phase` 參數 / `runner.set_phase` 不存在 / status 無 phase）

- [ ] **Step 3: 改 `web/runner.py`**

`_State` 加 `phase` 欄位（在 `last_change_counts` 之後）：

```python
@dataclass
class _State:
    running: bool = False
    last_run: str | None = None
    last_error: str | None = None
    last_failed_readers: list[str] = field(default_factory=list)
    last_change_counts: ChangeCounts = field(default_factory=ChangeCounts)
    phase: str = ""
```

`status()` 輸出 phase：

```python
def status() -> dict:
    return {
        "running": _state.running,
        "last_run": _state.last_run,
        "last_error": _state.last_error,
        "last_failed_readers": list(_state.last_failed_readers),
        "last_change_counts": _state.last_change_counts.model_dump(),
        "phase": _state.phase,
    }
```

新增 `set_phase`（放在 `end_browser` 之後）：

```python
def set_phase(name: str) -> None:
    """回報目前爬蟲階段（best-effort，供 stepper 顯示）。"""
    with _lock:
        _state.phase = name
```

`_run` 的 `finally` 清空 phase：

```python
def _run(launch_scrape: Callable[[], set[str]]) -> None:
    try:
        failed = launch_scrape()
        _state.last_error = None
        _state.last_failed_readers = sorted(failed or [])
        _state.last_run = datetime.now().isoformat(timespec="seconds")
    except LoginRequired:
        _state.last_error = "請先 career-sentinel login"
    except Exception as exc:  # noqa: BLE001 - 任何抓取失敗都記錄、不讓執行緒崩
        _state.last_error = str(exc)
    finally:
        end_browser()
        set_phase("")
```

`default_scrape` 逐階段回報（開始 establish、pipeline 前 digest；正常結束的清空由 `_run` finally 負責）：

```python
def default_scrape(db_path: str | None = None) -> set[str]:
    """真實抓取：scrape_session → run_pipeline 存。未登入 raise LoginRequired。需真瀏覽器。"""
    from .. import cli, config, store
    from ..scraper import real

    _state.last_change_counts = ChangeCounts()  # 先重置，避免失敗/未登入時殘留上次計數
    set_phase("establish")
    result = real.scrape_session(on_phase=set_phase)
    if result is None:
        raise LoginRequired()
    failed = result[1]
    conn = store.connect(db_path or config.db_path())
    try:
        set_phase("digest")
        _report, counts = cli.run_pipeline(lambda: result, conn, now=datetime.now().isoformat(timespec="seconds"))
        _state.last_change_counts = counts
    finally:
        conn.close()
    return failed
```

- [ ] **Step 4: 改 `scraper/real.py`**

`scrape` 加 `on_phase`、每個 reader 前回報：

```python
def scrape(page, on_phase=None) -> tuple[Snapshot, set[str]]:
    """逐讀取器抓取；單一失敗只記進 failed、不中斷其他。on_phase(name) 在每個 reader 前回報階段。"""
    readers = (
        ("viewers", fetch_viewers),
        ("applications", fetch_applications),
        ("messages", fetch_messages),
        ("interviews", fetch_interviews),
    )
    collected: dict[str, list] = {"viewers": [], "applications": [], "messages": [], "interviews": []}
    failed: set[str] = set()
    for name, fn in readers:
        if on_phase:
            on_phase(name)
        try:
            collected[name] = fn(page)
        except Exception:
            failed.add(name)
    snapshot = Snapshot(
        viewers=collected["viewers"],
        applications=collected["applications"],
        messages=collected["messages"],
        interviews=collected["interviews"],
    )
    return snapshot, failed
```

`scrape_session` 加 `on_phase` 並傳下去：

```python
def scrape_session(on_phase=None) -> tuple[Snapshot, set[str]] | None:
    """開 headful context → establish_session → scrape。未登入回 None。需真瀏覽器、不單測。"""
    from rebrowser_playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            if not establish_session(page):
                return None
            return scrape(page, on_phase=on_phase)
        finally:
            ctx.close()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_scrape_phase.py -q`
Expected: PASS（6 passed）

- [ ] **Step 6: 全測試回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（既有 252 + 新增；一個既有 Starlette DeprecationWarning 為預期）

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/web/runner.py sentinel/src/career_sentinel/scraper/real.py sentinel/tests/test_scrape_phase.py
git commit -m "feat(sentinel): 爬蟲階段回報 runner.phase + real.scrape on_phase（SP14）"
```

---

### Task 2：前端——全域爬蟲 stepper

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（`StatusResp` 加 `phase`）
- Create: `sentinel/web/frontend/src/ScrapeStepper.tsx`
- Modify: `sentinel/web/frontend/src/App.tsx`（頂部掛 stepper）
- 建置驗證：`npm run build`

**Interfaces:**
- Consumes: `GET /api/status` 現在回傳 `phase`（Task 1）。
- Produces: `ScrapeStepper`（default export，props `{ phase: string }`）。

- [ ] **Step 1: `api.ts` 的 `StatusResp` 加 `phase`**

把 `StatusResp` 介面改成含 `phase`（找到現有 `export interface StatusResp { running: boolean; last_run: string | null; last_error: string | null; last_failed_readers: string[]; last_change_counts: ChangeCounts }`）：

```typescript
export interface StatusResp { running: boolean; last_run: string | null; last_error: string | null; last_failed_readers: string[]; last_change_counts: ChangeCounts; phase: string }
```

- [ ] **Step 2: 建 `ScrapeStepper.tsx`**

Create `sentinel/web/frontend/src/ScrapeStepper.tsx`：

```tsx
import { Stepper } from "@mantine/core";

const STEPS = [
  { key: "establish", label: "建立連線" },
  { key: "viewers", label: "誰看過我" },
  { key: "applications", label: "應徵" },
  { key: "messages", label: "訊息" },
  { key: "interviews", label: "面試" },
  { key: "digest", label: "整理" },
];

export default function ScrapeStepper({ phase }: { phase: string }) {
  const active = STEPS.findIndex((s) => s.key === phase);
  if (active < 0) return null; // phase 空或不在清單 → 不顯示（閒置/同步爬蟲不觸發）
  return (
    <Stepper active={active} size="xs" p="md" pb={0} iconSize={22}>
      {STEPS.map((s) => (
        <Stepper.Step key={s.key} label={s.label} />
      ))}
    </Stepper>
  );
}
```

- [ ] **Step 3: `App.tsx` 頂部掛 stepper**

在 `App.tsx` 的 import 區加：

```typescript
import ScrapeStepper from "./ScrapeStepper";
```

在 `<AppShell.Main>` 內、`{due && (...)}` 橫幅**之前**加一行（`ScrapeStepper` 自身在 phase 不在清單時回 null，故不需再 gate `running`）：

```tsx
      <AppShell.Main>
        <ScrapeStepper phase={status.data?.phase ?? ""} />
        {due && (
```

- [ ] **Step 4: 前端建置驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: `✓ built`，零 TS 錯誤。

- [ ] **Step 5: 後端測試回歸（確認無牽連）**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠。

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/ScrapeStepper.tsx sentinel/web/frontend/src/App.tsx
git commit -m "feat(sentinel): 全域爬蟲階段 stepper（切分頁可見）（SP14）"
```

---

### Task 3：前端——單次等待 inline 計時（useElapsed + BusyHint + 各頁套用）

**Files:**
- Create: `sentinel/web/frontend/src/useElapsed.ts`
- Create: `sentinel/web/frontend/src/BusyHint.tsx`
- Modify: `sentinel/web/frontend/src/ResumePage.tsx`、`MatchPage.tsx`、`TailorPage.tsx`、`RecommendPage.tsx`、`SearchPage.tsx`、`Resume104Page.tsx`、`JobRow.tsx`
- 建置驗證：`npm run build`

**Interfaces:**
- Produces: `useElapsed(active: boolean): number`；`BusyHint`（default export，props `{ active: boolean; label: string }`）。

- [ ] **Step 1: 建 `useElapsed.ts`**

Create `sentinel/web/frontend/src/useElapsed.ts`：

```typescript
import { useEffect, useState } from "react";

/** active 為真時每秒 +1，轉 false 歸零。 */
export function useElapsed(active: boolean): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!active) {
      setN(0);
      return;
    }
    setN(0);
    const id = setInterval(() => setN((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
  return n;
}
```

- [ ] **Step 2: 建 `BusyHint.tsx`**

Create `sentinel/web/frontend/src/BusyHint.tsx`：

```tsx
import { Group, Loader, Text } from "@mantine/core";
import { useElapsed } from "./useElapsed";

/** 單次等待計時提示：active 時顯示「{label}…（已 N 秒）」。hook 必在 return 前呼叫。 */
export default function BusyHint({ active, label }: { active: boolean; label: string }) {
  const n = useElapsed(active);
  if (!active) return null;
  return (
    <Group gap={6} c="dimmed" mt={4}>
      <Loader size="xs" />
      <Text size="xs">{label}…（已 {n} 秒）</Text>
    </Group>
  );
}
```

- [ ] **Step 3: 各頁套用 BusyHint（每處：import + 在指定 Button 之後就近插入一行）**

每個檔案頂部加 import：`import BusyHint from "./BusyHint";`（放在其他相對匯入附近）。
然後在**指定按鈕之後**插入對應 `<BusyHint .../>`（就近放在同一容器內）：

| 檔案 | 錨點按鈕（現有） | 插入 | busy 變數 |
|---|---|---|---|
| `ResumePage.tsx` | `<Button onClick={runDiagnose} loading={busy} ...>` | `<BusyHint active={busy} label="分析中" />` | `busy` |
| `MatchPage.tsx` | `<Button onClick={run} loading={busy} ...>比對</Button>` | `<BusyHint active={busy} label="比對中" />` | `busy` |
| `TailorPage.tsx` | `<Button onClick={run} loading={busy} ...>`（客製化） | `<BusyHint active={busy} label="產生中" />` | `busy` |
| `TailorPage.tsx` | `<Button ... loading={applyBusy} ...>`（開投遞頁） | `<BusyHint active={applyBusy} label="開啟中" />` | `applyBusy` |
| `RecommendPage.tsx` | `<Button ... onClick={pull} loading={busy}>`（拉取推薦） | `<BusyHint active={busy} label="抓取中" />` | `busy` |
| `SearchPage.tsx` | `<Button onClick={run} loading={busy} ...>搜尋</Button>` | `<BusyHint active={busy} label="搜尋中" />` | `busy` |
| `Resume104Page.tsx` | `action={<Button onClick={read} loading={busy}>讀取我的 104 履歷</Button>}` | 在該 Paper/內容區塊放 `<BusyHint active={busy} label="讀取中" />` | `busy` |
| `Resume104Page.tsx` | `<Button ... onClick={runDiag} loading={diagBusy}>健檢</Button>` | `<BusyHint active={diagBusy} label="分析中" />` | `diagBusy` |
| `Resume104Page.tsx` | `<Button ... onClick={openEdit} loading={applyBusy}>開啟編輯頁</Button>` | `<BusyHint active={applyBusy} label="開啟中" />` | `applyBusy` |
| `JobRow.tsx` | `<Button ... onClick={run} loading={busy} disabled={!canMatch}>比對</Button>`（逐列比對，涵蓋推薦+搜尋列） | `<BusyHint active={busy} label="比對中" />` | `busy` |

> 放置原則：插在該按鈕所在的 `<Group>`/`<Stack>` **內、按鈕之後**（同層），維持版面。`BusyHint` 自身 `active=false` 時回 null，不佔位。
> Resume104Page 的「讀取」按鈕在 `PageHeader` 的 `action` prop 內（不便塞 hint），故把讀取的 `<BusyHint active={busy} label="讀取中" />` 放在主內容區塊頂部（讀取結果 Paper 之前）即可。
> **不動 `ResearchButton.tsx`**——它已有「上網研究中（約 20–60 秒）…」等待訊息，維持現狀（YAGNI、避免雙 Loader）。

- [ ] **Step 4: 前端建置驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: `✓ built`，零 TS 錯誤（特別注意：無未使用 import、`BusyHint` 每處 props 型別正確）。

- [ ] **Step 5: 後端測試回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠。

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/useElapsed.ts sentinel/web/frontend/src/BusyHint.tsx sentinel/web/frontend/src/ResumePage.tsx sentinel/web/frontend/src/MatchPage.tsx sentinel/web/frontend/src/TailorPage.tsx sentinel/web/frontend/src/RecommendPage.tsx sentinel/web/frontend/src/SearchPage.tsx sentinel/web/frontend/src/Resume104Page.tsx sentinel/web/frontend/src/JobRow.tsx
git commit -m "feat(sentinel): 單次等待 inline 計時 BusyHint（LLM/同步爬蟲各頁）（SP14）"
```

---

## 收尾（所有任務後）

- 最終全分支 review（opus）：重點驗 phase best-effort 不影響抓取、`_run` finally 一律清空 phase、stepper phase 不在清單自我隱藏（同步爬蟲不誤觸）、BusyHint hook 順序正確（`useElapsed` 在 return 前）、切分頁 stepper 仍可見、前端 build 乾淨、零後端回歸。
- 真機驗證（使用者）：重新抓取 → 頂部 stepper 隨階段前進、切分頁仍可見；跑健檢/比對/搜尋/推薦 → 按鈕旁「…（已 N 秒）」計時。
- roadmap「隨手記/技術債」補一筆（含本輪順帶修的「切分頁清空 local state（全分頁 keepMounted）」）。
- merge dev→main + push（自動部署——需明講）。
