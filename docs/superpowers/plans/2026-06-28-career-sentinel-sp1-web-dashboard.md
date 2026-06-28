# career-sentinel SP1 — 本地 Web 殼 + 儀表板 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** career-sentinel 從 CLI 長出本地 web app：FastAPI 伺服器 + React/Mantine 儀表板，呈現 `run` 的三類資料與彙整，並提供網頁「重新抓取」按鈕觸發實際 headful 爬取。

**Architecture:** 重用既有 `store`/`diff`/`digest`/`scraper`/`browser`。新增 `web/` 子套件（FastAPI `create_app` + 三個 JSON API + 背景抓取 runner）與 `web/frontend/`（React+Vite+Mantine 儀表板）。新增 `career-sentinel serve` 指令起 uvicorn。抓取在背景執行緒跑（headful Playwright），前端輪詢 `/api/status`。

**Tech Stack:** FastAPI、uvicorn、React 18、Vite、Mantine 7、TanStack Query、TypeScript、pytest。

## Global Constraints

- `sentinel/` 獨立，**不 import/依賴** `backend/`、`frontend/`（前端 theme/樣式用**複製**）；套件名 `career_sentinel`。
- 後端只綁 `127.0.0.1`（地端單人、不對外）。
- 抓取重用 Phase 2 的 `real.scrape` + `cli.run_pipeline`（存+容錯沿用）；**不改其行為**。
- `/api/snapshot` 的彙整文字用 `digest.render_human`（純本地、**不呼叫 LLM**），避免每次開頁打 LLM。
- 抓取在背景執行緒（headful，**headless 過不了 Cloudflare**）；同時只准一個。
- 後端 API 用 FastAPI `TestClient` + 暫時 SQLite 單測（不開瀏覽器）；`scrape_session`/`serve`/真實爬取不單測，靠一次手動驗證。
- 前端沿用雲端慣例：`npm run build` 通過為閘門 + 人工目視，無 FE 單元測試。
- 本地伺服器埠：`8765`。
- 驗證閘門：`cd sentinel && uv run pytest` 全綠；`cd sentinel/web/frontend && npm run build` 成功。
- Phase 1/2 既有測試不得回歸。

---

### Task 1: 後端依賴 + web 子套件骨架

**Files:**
- Modify: `sentinel/pyproject.toml`
- Create: `sentinel/src/career_sentinel/web/__init__.py`
- Test: `sentinel/tests/test_web_import.py`

**Interfaces:**
- Consumes：無。
- Produces：`career_sentinel.web` 子套件可匯入；fastapi/uvicorn 已安裝。

- [ ] **Step 1: 在 `pyproject.toml` 的 `dependencies` 加入 fastapi/uvicorn**

把 `dependencies` 陣列改成（在既有項目後加兩行）：

```toml
dependencies = [
    "rebrowser-playwright>=1.49",
    "pydantic>=2.7",
    "python-dotenv>=1.0",
    "httpx>=0.27",
    "fastapi>=0.110",
    "uvicorn>=0.29",
]
```

- [ ] **Step 2: 建立 `sentinel/src/career_sentinel/web/__init__.py`**

```python
"""career-sentinel 本地 web 介面（FastAPI + React 儀表板）。"""
```

- [ ] **Step 3: 寫 smoke 測試 `tests/test_web_import.py`**

```python
def test_web_package_imports():
    import career_sentinel.web  # noqa: F401
```

- [ ] **Step 4: 安裝並跑測試**

Run: `cd sentinel && uv sync && uv run pytest tests/test_web_import.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/pyproject.toml sentinel/uv.lock sentinel/src/career_sentinel/web/__init__.py sentinel/tests/test_web_import.py
git commit -m "feat(sentinel): web 子套件骨架 + fastapi/uvicorn 依賴"
```

---

### Task 2: `store.latest_run_at` 輔助

**Files:**
- Modify: `sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_store_run_at.py`

**Interfaces:**
- Consumes：`store.{connect,save_snapshot}`、`models.Snapshot`。
- Produces：`store.latest_run_at(conn) -> str | None`（最新快照的 run_at；無則 None）。

- [ ] **Step 1: 寫失敗測試 `tests/test_store_run_at.py`**

```python
from career_sentinel import store
from career_sentinel.models import Snapshot


def test_latest_run_at_none_when_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.latest_run_at(conn) is None


def test_latest_run_at_returns_newest(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(), run_at="2026-06-27T10:00:00")
    store.save_snapshot(conn, Snapshot(), run_at="2026-06-28T10:00:00")
    assert store.latest_run_at(conn) == "2026-06-28T10:00:00"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_store_run_at.py -v`
Expected: FAIL（`AttributeError: module ... has no attribute 'latest_run_at'`）。

- [ ] **Step 3: 在 `store.py` 末尾加 `latest_run_at`**

```python
def latest_run_at(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT run_at FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    return row[0] if row else None
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_store_run_at.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/store.py sentinel/tests/test_store_run_at.py
git commit -m "feat(sentinel): store.latest_run_at（最新快照時間）"
```

---

### Task 3: `real.scrape_session` 抽取 + `cli._cmd_run` 改用

**Files:**
- Modify: `sentinel/src/career_sentinel/scraper/real.py`
- Modify: `sentinel/src/career_sentinel/cli.py`（`_cmd_run`）

**Interfaces:**
- Consumes：`real.{establish_session,scrape}`、`browser.open_context`、`cli.run_pipeline`。
- Produces：`real.scrape_session() -> tuple[Snapshot, set[str]] | None`（開 headful context→establish→scrape；未登入回 None）。供 cli 與 web runner 共用。

**註：** `scrape_session`/`_cmd_run` 需真瀏覽器、不單測；以全測試不回歸 + 最終手動 `career-sentinel run` 驗證。

- [ ] **Step 1: 在 `real.py` 加 `scrape_session`**

在 `scraper/real.py` 末尾加入：

```python
def scrape_session() -> tuple[Snapshot, set[str]] | None:
    """開 headful context → establish_session → scrape。未登入回 None。需真瀏覽器、不單測。"""
    from rebrowser_playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            if not establish_session(page):
                return None
            return scrape(page)
        finally:
            ctx.close()
```

- [ ] **Step 2: 改 `cli._cmd_run` 改用 `scrape_session`**

把 `cli.py` 的 `_cmd_run` 整段替換為：

```python
def _cmd_run() -> int:
    from .scraper import real

    conn = store.connect(config.db_path())
    result = real.scrape_session()
    if result is None:
        print("尚未登入，請先執行：career-sentinel login")
        return 1
    report = run_pipeline(
        lambda: result,
        conn,
        now=datetime.now().isoformat(timespec="seconds"),
    )
    print(report)
    return 0
```

（`datetime`、`store`、`config`、`run_pipeline` 皆既有匯入；不再於 `_cmd_run` 內直接用 `sync_playwright`/`browser`。）

- [ ] **Step 3: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -v`
Expected: 全 PASS（`_cmd_run` 與 `scrape_session` 不被單測涵蓋，但既有測試不得壞）。

- [ ] **Step 4: Commit**

```bash
git add sentinel/src/career_sentinel/scraper/real.py sentinel/src/career_sentinel/cli.py
git commit -m "refactor(sentinel): 抽 real.scrape_session（瀏覽器生命週期），cli/web 共用"
```

---

### Task 4: 背景抓取 runner

**Files:**
- Create: `sentinel/src/career_sentinel/web/runner.py`
- Test: `sentinel/tests/test_web_runner.py`

**Interfaces:**
- Consumes：`real.scrape_session`、`cli.run_pipeline`、`store`、`config`。
- Produces：
  - `class LoginRequired(Exception)`
  - `status() -> dict`（`{running, last_run, last_error, last_failed_readers}`）
  - `start_scrape(launch_scrape) -> bool`（已在跑回 False；否則起背景執行緒、回 True）
  - `default_scrape() -> set[str]`（真實抓取：scrape_session→存；未登入 raise LoginRequired）

**測試策略：** `start_scrape` 吃可注入的 `launch_scrape`，測「拒絕並行 / 成功更新 last_run / 例外設 last_error / LoginRequired 設提示」皆不開瀏覽器。並行測試用一個會 block 的 launch 確保狀態為 running。

- [ ] **Step 1: 寫失敗測試 `tests/test_web_runner.py`**

```python
import time

from career_sentinel.web import runner


def _reset():
    runner._state.running = False
    runner._state.last_run = None
    runner._state.last_error = None
    runner._state.last_failed_readers = []


def test_start_scrape_success_updates_state():
    _reset()
    assert runner.start_scrape(lambda: {"viewers"}) is True
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    st = runner.status()
    assert st["running"] is False
    assert st["last_run"] is not None
    assert st["last_error"] is None
    assert st["last_failed_readers"] == ["viewers"]


def test_start_scrape_rejects_concurrent():
    _reset()
    gate = {"go": False}

    def slow():
        while not gate["go"]:
            time.sleep(0.01)
        return set()

    assert runner.start_scrape(slow) is True
    assert runner.start_scrape(lambda: set()) is False  # 已在跑
    gate["go"] = True
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    assert runner.status()["running"] is False


def test_start_scrape_login_required_sets_error():
    _reset()
    def needs_login():
        raise runner.LoginRequired()
    runner.start_scrape(needs_login)
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    assert runner.status()["last_error"] == "請先 career-sentinel login"


def test_start_scrape_exception_sets_error():
    _reset()
    def boom():
        raise RuntimeError("kaboom")
    runner.start_scrape(boom)
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    assert "kaboom" in runner.status()["last_error"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_runner.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `web/runner.py`**

```python
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable


class LoginRequired(Exception):
    """抓取時偵測到未登入。"""


@dataclass
class _State:
    running: bool = False
    last_run: str | None = None
    last_error: str | None = None
    last_failed_readers: list[str] = field(default_factory=list)


_state = _State()
_lock = threading.Lock()


def status() -> dict:
    return {
        "running": _state.running,
        "last_run": _state.last_run,
        "last_error": _state.last_error,
        "last_failed_readers": list(_state.last_failed_readers),
    }


def start_scrape(launch_scrape: Callable[[], set[str]]) -> bool:
    """已在跑回 False；否則起背景執行緒跑 launch_scrape、回 True。"""
    with _lock:
        if _state.running:
            return False
        _state.running = True
    threading.Thread(target=_run, args=(launch_scrape,), daemon=True).start()
    return True


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
        _state.running = False


def default_scrape() -> set[str]:
    """真實抓取：scrape_session → run_pipeline 存。未登入 raise LoginRequired。需真瀏覽器。"""
    from .. import cli, config, store
    from ..scraper import real

    result = real.scrape_session()
    if result is None:
        raise LoginRequired()
    snapshot, failed = result
    conn = store.connect(config.db_path())
    cli.run_pipeline(lambda: result, conn, now=datetime.now().isoformat(timespec="seconds"))
    return failed
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_web_runner.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/web/runner.py sentinel/tests/test_web_runner.py
git commit -m "feat(sentinel): web 背景抓取 runner（單例狀態 + 拒絕並行 + 容錯）"
```

---

### Task 5: FastAPI app + 三個 API

**Files:**
- Create: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_app.py`

**Interfaces:**
- Consumes：`store`、`diff.diff_against_last`、`digest.render_human`、`runner`、`config`、`models.Snapshot`。
- Produces：
  - `create_app(db_path: str | None = None) -> FastAPI`
  - `GET /api/snapshot`、`POST /api/scrape`、`GET /api/status`（合約見 spec）

- [ ] **Step 1: 寫失敗測試 `tests/test_web_app.py`**

```python
from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel.web import runner
from career_sentinel import store
from career_sentinel.models import Application, Message, Snapshot, Viewer


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_snapshot_empty(tmp_path):
    r = _client(tmp_path).get("/api/snapshot")
    assert r.status_code == 200
    body = r.json()
    assert body["run_at"] is None
    assert body["viewers"] == [] and body["applications"] == [] and body["messages"] == []
    assert "尚無資料" in body["digest"]


def test_snapshot_returns_stored(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        viewers=[Viewer(company="台積電", job_title="後端", viewed_at="2026-06-28")],
        applications=[Application(job_id="1", company="台積電", title="後端", status="已讀", applied_at="2026-06-20")],
        messages=[Message(thread_id="t1", company="台積電", last_message="想約面試", has_interview_invite=True)],
    ), run_at="2026-06-28T10:00:00")
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["run_at"] == "2026-06-28T10:00:00"
    assert body["viewers"][0]["company"] == "台積電"
    assert body["applications"][0]["status"] == "已讀"
    assert body["messages"][0]["has_interview_invite"] is True
    assert "台積電" in body["digest"]


def test_scrape_starts_and_rejects_concurrent(tmp_path, monkeypatch):
    calls = {"n": 0}
    def fake_start(launch):
        calls["n"] += 1
        return calls["n"] == 1  # 第一次 True、第二次 False
    monkeypatch.setattr(runner, "start_scrape", fake_start)
    c = _client(tmp_path)
    assert c.post("/api/scrape").json() == {"status": "running"}
    r2 = c.post("/api/scrape")
    assert r2.status_code == 409
    assert r2.json() == {"status": "already_running"}


def test_status_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "status", lambda: {"running": False, "last_run": "2026-06-28T10:00:00", "last_error": None, "last_failed_readers": []})
    body = _client(tmp_path).get("/api/status").json()
    assert body["running"] is False
    assert body["last_run"] == "2026-06-28T10:00:00"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `web/app.py`**

```python
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .. import config, diff, digest, store
from . import runner


def _snapshot_payload(conn) -> dict:
    ids = store.latest_two_ids(conn)
    if not ids:
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [],
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": runner.status()["last_failed_readers"],
        }
    sid = ids[0]
    snap = store.load_snapshot(conn, sid)
    d = diff.diff_against_last(conn, sid)
    return {
        "run_at": store.latest_run_at(conn),
        "viewers": [{"company": v.company, "job_title": v.job_title, "viewed_at": v.viewed_at} for v in snap.viewers],
        "applications": [{"job_id": a.job_id, "company": a.company, "title": a.title, "status": a.status, "applied_at": a.applied_at} for a in snap.applications],
        "messages": [{"thread_id": m.thread_id, "company": m.company, "last_message": m.last_message, "has_interview_invite": m.has_interview_invite} for m in snap.messages],
        "digest": digest.render_human(d, snap),
        "failed_readers": runner.status()["last_failed_readers"],
    }


def create_app(db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="career-sentinel")

    def _conn():
        return store.connect(db_path or str(config.db_path()))

    @app.get("/api/snapshot")
    def snapshot() -> dict:
        return _snapshot_payload(_conn())

    @app.post("/api/scrape")
    def scrape():
        if not runner.start_scrape(runner.default_scrape):
            return JSONResponse({"status": "already_running"}, status_code=409)
        return {"status": "running"}

    @app.get("/api/status")
    def status() -> dict:
        return runner.status()

    return app
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_app.py
git commit -m "feat(sentinel): FastAPI app + /api/snapshot·scrape·status"
```

---

### Task 6: `career-sentinel serve` 指令

**Files:**
- Modify: `sentinel/src/career_sentinel/cli.py`（`main` 加 `serve` 子命令 + `_cmd_serve`）
- Test: `sentinel/tests/test_cli_serve.py`

**Interfaces:**
- Consumes：`web.app.create_app`、`uvicorn`。
- Produces：`career-sentinel serve` 起 uvicorn（綁 127.0.0.1:8765）+ 開瀏覽器。

**註：** `_cmd_serve` 會阻塞跑伺服器、不單測其執行；只測 `serve` 被 parser 接受（dispatch 對）。

- [ ] **Step 1: 寫失敗測試 `tests/test_cli_serve.py`**

```python
from career_sentinel import cli


def test_serve_dispatches(monkeypatch):
    called = {"serve": False}
    monkeypatch.setattr(cli, "_cmd_serve", lambda: called.__setitem__("serve", True) or 0)
    rc = cli.main(["serve"])
    assert rc == 0
    assert called["serve"] is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_cli_serve.py -v`
Expected: FAIL（`serve` 尚非有效子命令 → `ArgumentError` → main 回 2，或 `_cmd_serve` 不存在）。

- [ ] **Step 3: 在 `cli.py` 加 `_cmd_serve` 與 `serve` 子命令**

在 `cli.py` 加入 `_cmd_serve`（放在 `_cmd_run` 之後）：

```python
def _cmd_serve() -> int:
    import threading
    import webbrowser

    import uvicorn

    from .web.app import create_app

    url = "http://127.0.0.1:8765"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"career-sentinel 儀表板：{url}（Ctrl+C 結束）")
    uvicorn.run(create_app(), host="127.0.0.1", port=8765, log_level="warning")
    return 0
```

並在 `main` 的子命令註冊區（`sub.add_parser("run", ...)` 那行附近）加：

```python
    sub.add_parser("serve", help="起本地 web 儀表板")
```

在 `main` 的分派區（`if args.cmd == "run": ...` 之後）加：

```python
    if args.cmd == "serve":
        return _cmd_serve()
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_cli_serve.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/cli.py sentinel/tests/test_cli_serve.py
git commit -m "feat(sentinel): career-sentinel serve（起本地 web 儀表板）"
```

---

### Task 7: React 前端儀表板

**Files:**
- Create: `sentinel/web/frontend/package.json`
- Create: `sentinel/web/frontend/tsconfig.json`
- Create: `sentinel/web/frontend/vite.config.ts`
- Create: `sentinel/web/frontend/index.html`
- Create: `sentinel/web/frontend/src/main.tsx`
- Create: `sentinel/web/frontend/src/api.ts`
- Create: `sentinel/web/frontend/src/Dashboard.tsx`
- Create: `sentinel/web/frontend/.gitignore`

**Interfaces:**
- Consumes：後端 `/api/snapshot`、`/api/scrape`、`/api/status`。
- Produces：可 `npm run build` 的 React 儀表板（dist/）。

- [ ] **Step 1: 建立 `package.json`**

```json
{
  "name": "career-sentinel-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@mantine/core": "^7.10.0",
    "@mantine/hooks": "^7.10.0",
    "@tanstack/react-query": "^5.40.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0"
  }
}
```

- [ ] **Step 2: 建立 `tsconfig.json`、`vite.config.ts`、`index.html`、`.gitignore`**

`tsconfig.json`：
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true
  },
  "include": ["src"]
}
```

`vite.config.ts`（dev 時 `/api` proxy 到後端；build 輸出 dist）：
```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "dist" },
});
```

`index.html`：
```html
<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>career-sentinel</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`.gitignore`：
```gitignore
node_modules/
dist/
```

- [ ] **Step 3: 建立 `src/api.ts`（型別 + fetch）**

```ts
export interface Viewer { company: string; job_title: string; viewed_at: string }
export interface Application { job_id: string; company: string; title: string; status: string; applied_at: string }
export interface Message { thread_id: string; company: string; last_message: string; has_interview_invite: boolean }
export interface SnapshotResp {
  run_at: string | null;
  viewers: Viewer[];
  applications: Application[];
  messages: Message[];
  digest: string;
  failed_readers: string[];
}
export interface StatusResp { running: boolean; last_run: string | null; last_error: string | null; last_failed_readers: string[] }

export async function getSnapshot(): Promise<SnapshotResp> {
  const r = await fetch("/api/snapshot");
  return r.json();
}
export async function getStatus(): Promise<StatusResp> {
  const r = await fetch("/api/status");
  return r.json();
}
export async function startScrape(): Promise<{ status: string }> {
  const r = await fetch("/api/scrape", { method: "POST" });
  return r.json();
}
```

- [ ] **Step 4: 建立 `src/Dashboard.tsx`**

```tsx
import { Badge, Button, Card, Container, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { getSnapshot, getStatus, startScrape } from "./api";

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card withBorder padding="md" radius="md" style={{ flex: 1, minWidth: 280 }}>
      <Title order={4} mb="sm">{title}（{count}）</Title>
      <Stack gap={8}>{children}</Stack>
    </Card>
  );
}

export default function Dashboard() {
  const qc = useQueryClient();
  const [polling, setPolling] = useState(false);

  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({
    queryKey: ["status"],
    queryFn: getStatus,
    refetchInterval: polling ? 2000 : false,
  });

  if (polling && status.data && !status.data.running) {
    setPolling(false);
    qc.invalidateQueries({ queryKey: ["snapshot"] });
  }

  async function refresh() {
    const r = await startScrape();
    if (r.status === "already_running") { setPolling(true); return; }
    setPolling(true);
  }

  const s = snap.data;
  const running = polling || status.data?.running;

  return (
    <Container size="lg" py="lg">
      <Group justify="space-between" mb="md">
        <Title order={2}>career-sentinel</Title>
        <Group>
          <Text size="sm" c="dimmed">上次更新：{s?.run_at ?? "—"}</Text>
          <Button onClick={refresh} loading={running} disabled={running}>重新抓取</Button>
        </Group>
      </Group>

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
            <Text key={i} size="sm">{v.company}　<Text span c="dimmed">{v.job_title} · {v.viewed_at}</Text></Text>
          ))}
        </Panel>
        <Panel title="我的應徵" count={s?.applications.length ?? 0}>
          {s?.applications.map((a) => (
            <Text key={a.job_id} size="sm">{a.company} · {a.title}　<Badge size="sm" variant="light">{a.status}</Badge></Text>
          ))}
        </Panel>
        <Panel title="訊息 · 面試" count={s?.messages.length ?? 0}>
          {s?.messages.map((m) => (
            <Text key={m.thread_id} size="sm">
              {m.has_interview_invite && <Badge size="sm" color="orange" mr={6}>面試</Badge>}
              {m.company}：<Text span c="dimmed">{m.last_message}</Text>
            </Text>
          ))}
        </Panel>
      </Group>
    </Container>
  );
}
```

- [ ] **Step 5: 建立 `src/main.tsx`（MantineProvider + QueryClient）**

```tsx
import { MantineProvider } from "@mantine/core";
import "@mantine/core/styles.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import Dashboard from "./Dashboard";

const qc = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider defaultColorScheme="dark">
      <QueryClientProvider client={qc}>
        <Dashboard />
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 6: 安裝並建置（閘門）**

Run: `cd sentinel/web/frontend && npm install && npm run build`
Expected: `tsc -b && vite build` 無型別錯誤、`✓ built` 成功、產出 `dist/`。

> 註：本 SP1 用 Mantine 預設深色主題（標準色），**先求功能可用**；視覺對齊雲端 Cockpit 風
> （複製 `theme.ts`/`.jt-*` 樣式、tangerine/teal 雙訊號色）已列入 roadmap，留後續主題 polish。

- [ ] **Step 7: Commit**

```bash
git add sentinel/web/frontend/package.json sentinel/web/frontend/package-lock.json sentinel/web/frontend/tsconfig.json sentinel/web/frontend/vite.config.ts sentinel/web/frontend/index.html sentinel/web/frontend/.gitignore sentinel/web/frontend/src
git commit -m "feat(sentinel): React 儀表板（三面板 + 彙整 + 重新抓取輪詢）"
```

---

### Task 8: FastAPI 服務靜態 dist + 真機整合驗證

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`（掛載 dist 靜態檔）
- Test: `sentinel/tests/test_web_static.py`

**Interfaces:**
- Consumes：`create_app`、前端 `dist/`。
- Produces：`create_app` 在 `dist/` 存在時於 `/` 服務 SPA。

- [ ] **Step 1: 寫測試 `tests/test_web_static.py`（dist 不存在時 /api 仍正常、不崩）**

```python
from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp


def test_api_works_without_dist(tmp_path):
    # 未建置前端時，create_app 不應因缺 dist 而崩；/api 仍可用
    c = TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))
    assert c.get("/api/snapshot").status_code == 200
```

- [ ] **Step 2: 跑測試確認通過（現況已通，作為回歸保護）**

Run: `cd sentinel && uv run pytest tests/test_web_static.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 3: 在 `app.py` 的 `create_app` 末尾（`return app` 前）加靜態掛載**

```python
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    dist = Path(__file__).resolve().parents[3] / "web" / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="spa")
```

（`parents[3]`：`app.py`→`web`→`career_sentinel`→`src`→`sentinel`，故 `sentinel/web/frontend/dist`。掛載在所有 `/api` 路由註冊**之後**，故 API 優先。）

- [ ] **Step 4: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS（dist 不存在時掛載被跳過）。

- [ ] **Step 5: 真機整合驗證（需已 build 前端、已 login、登入態在 profile）**

Run（兩個終端機，或先 build 再 serve）：
```bash
cd sentinel/web/frontend && npm run build
cd ../.. && uv run career-sentinel serve
```
瀏覽器開 `http://127.0.0.1:8765`，預期：
- 看到三面板（誰看過我/應徵/訊息）+ 今日彙整 + 上次更新時間。
- 按「重新抓取」→ 彈 headful Chrome 實際爬一次 → 按鈕 loading → 爬完畫面更新（數字/清單變動）。
- 未登入時頂部顯示「請先 career-sentinel login」。

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_static.py
git commit -m "feat(sentinel): FastAPI 服務前端 dist 靜態檔 + 整合驗證"
```

---

## 完成後

`career-sentinel serve` 起本地儀表板、看三類資料與彙整、網頁觸發抓取。接 SP2（設定 + 關注清單），見 [../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)。即時進度（SSE）、通知於後續 SP 補。
