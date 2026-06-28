# 104 地端哨兵 career-sentinel — MVP Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一個獨立地端 Python CLI，端到端跑通「開已登入 Chrome → 取得求職資料 → 存 SQLite 快照 → 跟上次比對差異 → LLM 彙整 → 印出」的完整管線；爬蟲在本階段先用假資料 stub，並用一個 spike 任務擷取真 104 回應存成 fixture 供 Phase 2。

**Architecture:** 模組各司其職、介面明確、可獨立測：`config`（設定/路徑）、`models`（Pydantic 型別）、`store`（SQLite 快照 + 差異）、`digest`（LLM 彙整，純 prompt 組裝與 HTTP 呼叫分離）、`browser`（Playwright 持久化 profile + 登入偵測）、`scraper/fake`（本階段假資料）、`cli`（login / run）。爬蟲「抓取（需真瀏覽器、不單測）」與「解析（純函式、可單測）」分離。

**Tech Stack:** Python 3.12+、uv、Playwright（sync API）、Pydantic v2、python-dotenv、httpx、pytest。

## Global Constraints

- 全新獨立程式，放在現有 monorepo 的頂層資料夾 `sentinel/`，**不 import、不依賴** `backend/` 或 `frontend/`。
- **絕不儲存 104 帳號密碼**：登入態一律靠 Playwright 持久化 Chrome profile（`launch_persistent_context`）。
- LLM key 自帶，只從 `.env` 讀，不寫死、不進 git（`.env` 須在 `.gitignore`）。
- 容錯哲學：單一讀取器失敗只標記該類失敗、不污染快照、其他照跑（沿用主專案 analyze 單筆失敗跳過的做法）。
- 抓取與解析分離：解析為吃 dict/HTML 回傳型別模型的純函式，可不連線單測。
- Python 套件名 `career_sentinel`；指令名 `career-sentinel`。
- 驗證閘門：`cd sentinel && uv run pytest` 全綠；端到端 `run`（假資料）能印出彙整。
- 所有 SQLite 時間以 ISO8601 字串存（地端單人、零時區糾結）。

---

### Task 1: 專案骨架（uv 專案 + 套件結構 + pytest 可跑）

**Files:**
- Create: `sentinel/pyproject.toml`
- Create: `sentinel/.gitignore`
- Create: `sentinel/.env.example`
- Create: `sentinel/README.md`
- Create: `sentinel/src/career_sentinel/__init__.py`
- Create: `sentinel/tests/__init__.py`
- Create: `sentinel/tests/test_smoke.py`

**Interfaces:**
- Consumes: 無。
- Produces: 可安裝的 `career_sentinel` 套件、可執行的 `uv run pytest`。

- [ ] **Step 1: 建立 `sentinel/pyproject.toml`**

```toml
[project]
name = "career-sentinel"
version = "0.1.0"
description = "104 地端哨兵：地端讀取求職狀態、比對變化、LLM 每日彙整"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.44",
    "pydantic>=2.7",
    "python-dotenv>=1.0",
    "httpx>=0.27",
]

[project.scripts]
career-sentinel = "career_sentinel.cli:main"

[dependency-groups]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/career_sentinel"]
```

- [ ] **Step 2: 建立 `sentinel/.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.env
data/
.pytest_cache/
```

- [ ] **Step 3: 建立 `sentinel/.env.example`**

```dotenv
# LLM（自帶 key，OpenAI 相容 chat completions 端點）
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=
LLM_MODEL=anthropic/claude-sonnet-4-6

# 選填：覆寫資料目錄（預設 sentinel/data）
# SENTINEL_DATA_DIR=
```

- [ ] **Step 4: 建立 `sentinel/README.md`**

```markdown
# career-sentinel — 104 地端哨兵

地端、單人、自帶 key 的求職助手。Playwright 驅動專用 Chrome profile（不存帳密），
讀 104 登入後的「誰看過我 / 投遞狀態 / 訊息」，存 SQLite 快照、跟上次比對變化、LLM 彙整。

## 安裝
    cd sentinel
    uv sync
    uv run playwright install chromium

## 使用
    cp .env.example .env   # 填 LLM key
    uv run career-sentinel login   # 首次：開 Chrome 手動登入 104
    uv run career-sentinel run     # 平常：擷取 → 比對 → 彙整
```

- [ ] **Step 5: 建立空套件與 smoke 測試**

`sentinel/src/career_sentinel/__init__.py`：
```python
__version__ = "0.1.0"
```

`sentinel/tests/__init__.py`：（空檔）

`sentinel/tests/test_smoke.py`：
```python
import career_sentinel


def test_package_imports():
    assert career_sentinel.__version__ == "0.1.0"
```

- [ ] **Step 6: 安裝並跑測試確認骨架可動**

Run: `cd sentinel && uv sync && uv run pytest tests/test_smoke.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 7: Commit**

```bash
git add sentinel/pyproject.toml sentinel/.gitignore sentinel/.env.example sentinel/README.md sentinel/src sentinel/tests
git commit -m "feat(sentinel): 專案骨架（uv 套件結構 + pytest smoke）"
```

---

### Task 2: 設定模組（路徑與 LLM 環境變數）

**Files:**
- Create: `sentinel/src/career_sentinel/config.py`
- Test: `sentinel/tests/test_config.py`

**Interfaces:**
- Consumes: 無。
- Produces：
  - `data_dir() -> Path`、`profile_dir() -> Path`、`db_path() -> Path`
  - `llm_settings() -> LlmSettings`（具 `base_url: str`、`api_key: str`、`model: str`）

- [ ] **Step 1: 寫失敗測試 `tests/test_config.py`**

```python
from career_sentinel import config


def test_data_dir_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path))
    assert config.data_dir() == tmp_path
    assert config.profile_dir() == tmp_path / "chrome-profile"
    assert config.db_path() == tmp_path / "sentinel.db"


def test_llm_settings_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    s = config.llm_settings()
    assert (s.base_url, s.api_key, s.model) == ("https://x/v1", "k", "m")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError` 或 `AttributeError`）。

- [ ] **Step 3: 實作 `config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_ROOT = Path(__file__).resolve().parents[2]  # sentinel/


def data_dir() -> Path:
    return Path(os.getenv("SENTINEL_DATA_DIR") or (_ROOT / "data"))


def profile_dir() -> Path:
    return data_dir() / "chrome-profile"


def db_path() -> Path:
    return data_dir() / "sentinel.db"


@dataclass(frozen=True)
class LlmSettings:
    base_url: str
    api_key: str
    model: str


def llm_settings() -> LlmSettings:
    return LlmSettings(
        base_url=os.getenv("LLM_BASE_URL", ""),
        api_key=os.getenv("LLM_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "anthropic/claude-sonnet-4-6"),
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_config.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/config.py sentinel/tests/test_config.py
git commit -m "feat(sentinel): 設定模組（資料路徑 + LLM 環境變數）"
```

---

### Task 3: 型別模型（Viewer / Application / Message / Snapshot / Diff）

**Files:**
- Create: `sentinel/src/career_sentinel/models.py`
- Test: `sentinel/tests/test_models.py`

**Interfaces:**
- Consumes: 無。
- Produces（後續 store / scraper / digest 全靠這些型別）：
  - `Viewer(company: str, job_title: str, viewed_at: str, raw: dict)`，鍵 `(company, job_title)`
  - `Application(job_id: str, company: str, title: str, status: str, applied_at: str, raw: dict)`，鍵 `job_id`
  - `Message(thread_id: str, company: str, last_message: str, has_interview_invite: bool, invite_date: str | None, raw: dict)`，鍵 `thread_id`
  - `Snapshot(viewers: list[Viewer], applications: list[Application], messages: list[Message])`
  - `StatusChange(application: Application, old_status: str, new_status: str)`
  - `Diff(new_viewers, status_changes: list[StatusChange], new_messages, new_invites)`，含 `is_empty() -> bool`

- [ ] **Step 1: 寫失敗測試 `tests/test_models.py`**

```python
from career_sentinel.models import (
    Application, Diff, Message, Snapshot, StatusChange, Viewer,
)


def test_models_build_with_defaults():
    v = Viewer(company="A", job_title="後端", viewed_at="2026-06-28")
    assert v.raw == {}
    a = Application(job_id="1", company="A", title="後端", status="已讀", applied_at="2026-06-20")
    m = Message(thread_id="t1", company="A", last_message="您好")
    assert m.has_interview_invite is False and m.invite_date is None
    snap = Snapshot(viewers=[v], applications=[a], messages=[m])
    assert len(snap.viewers) == 1


def test_diff_is_empty():
    assert Diff().is_empty() is True
    d = Diff(new_viewers=[Viewer(company="A", job_title="x", viewed_at="t")])
    assert d.is_empty() is False


def test_status_change_holds_old_and_new():
    a = Application(job_id="1", company="A", title="x", status="邀請面試", applied_at="t")
    sc = StatusChange(application=a, old_status="已讀", new_status="邀請面試")
    assert sc.old_status == "已讀" and sc.new_status == "邀請面試"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_models.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `models.py`**

```python
from __future__ import annotations

from pydantic import BaseModel, Field


class Viewer(BaseModel):
    company: str
    job_title: str
    viewed_at: str
    raw: dict = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.company, self.job_title)


class Application(BaseModel):
    job_id: str
    company: str
    title: str
    status: str
    applied_at: str
    raw: dict = Field(default_factory=dict)


class Message(BaseModel):
    thread_id: str
    company: str
    last_message: str
    has_interview_invite: bool = False
    invite_date: str | None = None
    raw: dict = Field(default_factory=dict)


class Snapshot(BaseModel):
    viewers: list[Viewer] = Field(default_factory=list)
    applications: list[Application] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)


class StatusChange(BaseModel):
    application: Application
    old_status: str
    new_status: str


class Diff(BaseModel):
    new_viewers: list[Viewer] = Field(default_factory=list)
    status_changes: list[StatusChange] = Field(default_factory=list)
    new_messages: list[Message] = Field(default_factory=list)
    new_invites: list[Message] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.new_viewers or self.status_changes
            or self.new_messages or self.new_invites
        )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_models.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/tests/test_models.py
git commit -m "feat(sentinel): 型別模型（Viewer/Application/Message/Snapshot/Diff）"
```

---

### Task 4: SQLite 存取（建表 + 存快照 + 讀快照）

**Files:**
- Create: `sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_store.py`

**Interfaces:**
- Consumes: `models.Snapshot/Viewer/Application/Message`。
- Produces：
  - `connect(path) -> sqlite3.Connection`（自動建表）
  - `save_snapshot(conn, snapshot: Snapshot, run_at: str) -> int`（回傳 snapshot_id）
  - `load_snapshot(conn, snapshot_id: int) -> Snapshot`
  - `latest_two_ids(conn) -> list[int]`（新到舊，最多兩個）

- [ ] **Step 1: 寫失敗測試 `tests/test_store.py`**

```python
from career_sentinel import store
from career_sentinel.models import Application, Message, Snapshot, Viewer


def _snap():
    return Snapshot(
        viewers=[Viewer(company="A", job_title="後端", viewed_at="2026-06-28", raw={"x": 1})],
        applications=[Application(job_id="j1", company="A", title="後端", status="已讀", applied_at="2026-06-20")],
        messages=[Message(thread_id="t1", company="A", last_message="您好", has_interview_invite=True, invite_date="2026-07-01")],
    )


def test_save_and_load_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    sid = store.save_snapshot(conn, _snap(), run_at="2026-06-28T10:00:00")
    loaded = store.load_snapshot(conn, sid)
    assert loaded.viewers[0].company == "A"
    assert loaded.viewers[0].raw == {"x": 1}
    assert loaded.applications[0].job_id == "j1"
    assert loaded.messages[0].has_interview_invite is True
    assert loaded.messages[0].invite_date == "2026-07-01"


def test_latest_two_ids_orders_new_to_old(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    s1 = store.save_snapshot(conn, _snap(), run_at="2026-06-27T10:00:00")
    s2 = store.save_snapshot(conn, _snap(), run_at="2026-06-28T10:00:00")
    assert store.latest_two_ids(conn) == [s2, s1]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_store.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `store.py`**

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import Application, Message, Snapshot, Viewer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS viewers (
    snapshot_id INTEGER, company TEXT, job_title TEXT, viewed_at TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    snapshot_id INTEGER, job_id TEXT, company TEXT, title TEXT,
    status TEXT, applied_at TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    snapshot_id INTEGER, thread_id TEXT, company TEXT, last_message TEXT,
    has_interview_invite INTEGER, invite_date TEXT, raw_json TEXT
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    return conn


def save_snapshot(conn: sqlite3.Connection, snapshot: Snapshot, run_at: str) -> int:
    cur = conn.execute("INSERT INTO snapshots (run_at) VALUES (?)", (run_at,))
    sid = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO viewers VALUES (?,?,?,?,?)",
        [(sid, v.company, v.job_title, v.viewed_at, json.dumps(v.raw, ensure_ascii=False)) for v in snapshot.viewers],
    )
    conn.executemany(
        "INSERT INTO applications VALUES (?,?,?,?,?,?,?)",
        [(sid, a.job_id, a.company, a.title, a.status, a.applied_at, json.dumps(a.raw, ensure_ascii=False)) for a in snapshot.applications],
    )
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?,?)",
        [(sid, m.thread_id, m.company, m.last_message, int(m.has_interview_invite), m.invite_date, json.dumps(m.raw, ensure_ascii=False)) for m in snapshot.messages],
    )
    conn.commit()
    return sid


def load_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> Snapshot:
    viewers = [
        Viewer(company=c, job_title=t, viewed_at=va, raw=json.loads(rj))
        for c, t, va, rj in conn.execute(
            "SELECT company, job_title, viewed_at, raw_json FROM viewers WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    applications = [
        Application(job_id=j, company=c, title=t, status=s, applied_at=aa, raw=json.loads(rj))
        for j, c, t, s, aa, rj in conn.execute(
            "SELECT job_id, company, title, status, applied_at, raw_json FROM applications WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    messages = [
        Message(thread_id=th, company=c, last_message=lm, has_interview_invite=bool(hi), invite_date=idt, raw=json.loads(rj))
        for th, c, lm, hi, idt, rj in conn.execute(
            "SELECT thread_id, company, last_message, has_interview_invite, invite_date, raw_json FROM messages WHERE snapshot_id=?", (snapshot_id,)
        )
    ]
    return Snapshot(viewers=viewers, applications=applications, messages=messages)


def latest_two_ids(conn: sqlite3.Connection) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 2")]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_store.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/store.py sentinel/tests/test_store.py
git commit -m "feat(sentinel): SQLite 存取（建表 + 存/讀快照）"
```

---

### Task 5: 差異比對（diff_against_last）

**Files:**
- Create: `sentinel/src/career_sentinel/diff.py`
- Test: `sentinel/tests/test_diff.py`

**Interfaces:**
- Consumes: `models.{Snapshot,Diff,StatusChange}`。
- Produces：
  - `compute_diff(previous: Snapshot | None, current: Snapshot) -> Diff`（純函式，本任務核心）
  - `diff_against_last(conn, current_id: int) -> Diff`（從 store 載最近兩筆後呼叫 `compute_diff`）

**比對規則：** previous 為 None（首次）→ 全部視為新。viewers 以 `(company, job_title)` 為鍵取新增；applications 以 `job_id` 為鍵、`status` 變動列入 `status_changes`；messages 以 `thread_id` 為鍵，新 thread 或 `last_message` 改變列入 `new_messages`；`has_interview_invite` 為 true 且（新 thread 或前次為 false）列入 `new_invites`。

- [ ] **Step 1: 寫失敗測試 `tests/test_diff.py`**

```python
from career_sentinel.diff import compute_diff
from career_sentinel.models import Application, Message, Snapshot, Viewer


def test_first_run_everything_is_new():
    cur = Snapshot(
        viewers=[Viewer(company="A", job_title="後端", viewed_at="t")],
        messages=[Message(thread_id="t1", company="A", last_message="hi", has_interview_invite=True)],
    )
    d = compute_diff(None, cur)
    assert len(d.new_viewers) == 1
    assert len(d.new_invites) == 1


def test_new_viewer_detected():
    prev = Snapshot(viewers=[Viewer(company="A", job_title="後端", viewed_at="t")])
    cur = Snapshot(viewers=[
        Viewer(company="A", job_title="後端", viewed_at="t"),
        Viewer(company="B", job_title="前端", viewed_at="t2"),
    ])
    d = compute_diff(prev, cur)
    assert [v.company for v in d.new_viewers] == ["B"]


def test_status_change_detected():
    prev = Snapshot(applications=[Application(job_id="j1", company="A", title="x", status="已讀", applied_at="t")])
    cur = Snapshot(applications=[Application(job_id="j1", company="A", title="x", status="邀請面試", applied_at="t")])
    d = compute_diff(prev, cur)
    assert len(d.status_changes) == 1
    assert d.status_changes[0].old_status == "已讀"
    assert d.status_changes[0].new_status == "邀請面試"


def test_new_invite_only_when_flag_flips_true():
    prev = Snapshot(messages=[Message(thread_id="t1", company="A", last_message="hi", has_interview_invite=False)])
    cur = Snapshot(messages=[Message(thread_id="t1", company="A", last_message="要約面試", has_interview_invite=True, invite_date="2026-07-01")])
    d = compute_diff(prev, cur)
    assert len(d.new_invites) == 1
    assert len(d.new_messages) == 1  # last_message 也變了


def test_no_change_is_empty():
    snap = Snapshot(applications=[Application(job_id="j1", company="A", title="x", status="已讀", applied_at="t")])
    assert compute_diff(snap, snap).is_empty()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_diff.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `diff.py`**

```python
from __future__ import annotations

import sqlite3

from . import store
from .models import Diff, Snapshot, StatusChange


def compute_diff(previous: Snapshot | None, current: Snapshot) -> Diff:
    prev = previous or Snapshot()

    prev_viewer_keys = {v.key for v in prev.viewers}
    new_viewers = [v for v in current.viewers if v.key not in prev_viewer_keys]

    prev_apps = {a.job_id: a for a in prev.applications}
    status_changes = [
        StatusChange(application=a, old_status=prev_apps[a.job_id].status, new_status=a.status)
        for a in current.applications
        if a.job_id in prev_apps and prev_apps[a.job_id].status != a.status
    ]

    prev_msgs = {m.thread_id: m for m in prev.messages}
    new_messages = [
        m for m in current.messages
        if m.thread_id not in prev_msgs or prev_msgs[m.thread_id].last_message != m.last_message
    ]
    new_invites = [
        m for m in current.messages
        if m.has_interview_invite
        and (m.thread_id not in prev_msgs or not prev_msgs[m.thread_id].has_interview_invite)
    ]

    return Diff(
        new_viewers=new_viewers,
        status_changes=status_changes,
        new_messages=new_messages,
        new_invites=new_invites,
    )


def diff_against_last(conn: sqlite3.Connection, current_id: int) -> Diff:
    ids = store.latest_two_ids(conn)
    current = store.load_snapshot(conn, current_id)
    previous = None
    for sid in ids:
        if sid != current_id:
            previous = store.load_snapshot(conn, sid)
            break
    return compute_diff(previous, current)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_diff.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/diff.py sentinel/tests/test_diff.py
git commit -m "feat(sentinel): 差異比對（新增看過我/狀態變動/新訊息/新邀約）"
```

---

### Task 6: LLM 彙整（prompt 組裝純函式 + HTTP 呼叫分離）

**Files:**
- Create: `sentinel/src/career_sentinel/digest.py`
- Test: `sentinel/tests/test_digest.py`

**Interfaces:**
- Consumes: `models.{Diff,Snapshot}`、`config.llm_settings`。
- Produces：
  - `build_prompt(diff: Diff, snapshot: Snapshot) -> str`（純函式，可單測）
  - `summarize(diff, snapshot, *, client=None) -> str`（無 key 或無變化時走本地後援，不呼叫 LLM）

**設計：** 無變化（`diff.is_empty()`）或未設 `api_key` → 回本地後援字串、**不**呼叫 LLM。HTTP 用 OpenAI 相容 `POST {base_url}/chat/completions`，`client` 可注入以利測試。

- [ ] **Step 1: 寫失敗測試 `tests/test_digest.py`**

```python
from career_sentinel import digest
from career_sentinel.config import LlmSettings
from career_sentinel.models import Diff, Snapshot, Viewer


def test_build_prompt_mentions_new_viewer():
    d = Diff(new_viewers=[Viewer(company="台積電", job_title="後端", viewed_at="2026-06-28")])
    text = digest.build_prompt(d, Snapshot())
    assert "台積電" in text
    assert "後端" in text


def test_summarize_no_change_uses_local_fallback(monkeypatch):
    monkeypatch.setattr(digest, "llm_settings", lambda: LlmSettings("", "", "m"))
    out = digest.summarize(Diff(), Snapshot())
    assert "沒有新變化" in out


def test_summarize_no_key_uses_local_fallback(monkeypatch):
    monkeypatch.setattr(digest, "llm_settings", lambda: LlmSettings("https://x/v1", "", "m"))
    d = Diff(new_viewers=[Viewer(company="台積電", job_title="後端", viewed_at="t")])
    out = digest.summarize(d, Snapshot())
    assert "台積電" in out  # 後援直接列出變化


def test_summarize_calls_llm_when_configured(monkeypatch):
    monkeypatch.setattr(digest, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    captured = {}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return {"choices": [{"message": {"content": "今日彙整：有人看你"}}]}

    class FakeClient:
        def post(self, url, **kw):
            captured["url"] = url
            captured["json"] = kw["json"]
            return FakeResp()

    d = Diff(new_viewers=[Viewer(company="A", job_title="x", viewed_at="t")])
    out = digest.summarize(d, Snapshot(), client=FakeClient())
    assert out == "今日彙整：有人看你"
    assert captured["url"] == "https://x/v1/chat/completions"
    assert captured["json"]["model"] == "m"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_digest.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `digest.py`**

```python
from __future__ import annotations

import httpx

from .config import llm_settings
from .models import Diff, Snapshot


def build_prompt(diff: Diff, snapshot: Snapshot) -> str:
    lines: list[str] = ["以下是使用者 104 求職狀態自上次以來的變化，請用繁體中文寫一段精簡的今日彙整："]
    if diff.new_viewers:
        lines.append("\n[新看過我的公司]")
        lines += [f"- {v.company}（{v.job_title}）{v.viewed_at}" for v in diff.new_viewers]
    if diff.status_changes:
        lines.append("\n[投遞狀態變動]")
        lines += [f"- {c.application.company} {c.application.title}：{c.old_status} → {c.new_status}" for c in diff.status_changes]
    if diff.new_messages:
        lines.append("\n[新訊息]")
        lines += [f"- {m.company}：{m.last_message}" for m in diff.new_messages]
    if diff.new_invites:
        lines.append("\n[面試邀約]")
        lines += [f"- {m.company}（邀約日期：{m.invite_date or '未定'}）" for m in diff.new_invites]
    lines.append(f"\n目前共投遞 {len(snapshot.applications)} 筆、累計 {len(snapshot.viewers)} 家看過你。")
    return "\n".join(lines)


def _local_fallback(diff: Diff, snapshot: Snapshot) -> str:
    if diff.is_empty():
        return "今日沒有新變化。"
    return build_prompt(diff, snapshot)


def summarize(diff: Diff, snapshot: Snapshot, *, client: object | None = None) -> str:
    cfg = llm_settings()
    if diff.is_empty() or not cfg.api_key:
        return _local_fallback(diff, snapshot)

    http = client or httpx.Client(timeout=60)
    resp = http.post(
        f"{cfg.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {cfg.api_key}"},
        json={
            "model": cfg.model,
            "messages": [{"role": "user", "content": build_prompt(diff, snapshot)}],
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_digest.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/digest.py sentinel/tests/test_digest.py
git commit -m "feat(sentinel): LLM 每日彙整（prompt 純函式 + OpenAI 相容呼叫 + 本地後援）"
```

---

### Task 7: 假爬蟲 stub（讓管線端到端跑得起來）

**Files:**
- Create: `sentinel/src/career_sentinel/scraper/__init__.py`
- Create: `sentinel/src/career_sentinel/scraper/fake.py`
- Test: `sentinel/tests/test_fake_scraper.py`

**Interfaces:**
- Consumes: `models.Snapshot`。
- Produces：
  - `fake.scrape() -> Snapshot`（回傳固定假資料，Phase 2 由真爬蟲 `scraper.scrape(page)` 取代）

- [ ] **Step 1: 寫失敗測試 `tests/test_fake_scraper.py`**

```python
from career_sentinel.scraper import fake
from career_sentinel.models import Snapshot


def test_fake_scrape_returns_populated_snapshot():
    snap = fake.scrape()
    assert isinstance(snap, Snapshot)
    assert snap.viewers and snap.applications and snap.messages
    assert any(m.has_interview_invite for m in snap.messages)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_fake_scraper.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 stub**

`sentinel/src/career_sentinel/scraper/__init__.py`：（空檔）

`sentinel/src/career_sentinel/scraper/fake.py`：
```python
from __future__ import annotations

from ..models import Application, Message, Snapshot, Viewer


def scrape() -> Snapshot:
    """本階段假資料；Phase 2 由真爬蟲取代。"""
    return Snapshot(
        viewers=[
            Viewer(company="台積電", job_title="資深後端工程師", viewed_at="2026-06-28 09:12"),
            Viewer(company="聯發科", job_title="平台軟體工程師", viewed_at="2026-06-27 18:40"),
        ],
        applications=[
            Application(job_id="j-1001", company="台積電", title="資深後端工程師", status="邀請面試", applied_at="2026-06-20"),
            Application(job_id="j-1002", company="某新創", title="全端工程師", status="不適合", applied_at="2026-06-18"),
        ],
        messages=[
            Message(thread_id="th-1", company="台積電", last_message="想邀請您本週四面試", has_interview_invite=True, invite_date="2026-07-03"),
            Message(thread_id="th-2", company="某新創", last_message="感謝您的應徵", has_interview_invite=False),
        ],
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_fake_scraper.py -v`
Expected: PASS（1 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/scraper sentinel/tests/test_fake_scraper.py
git commit -m "feat(sentinel): 假爬蟲 stub（供管線端到端開發）"
```

---

### Task 8: 瀏覽器登入殼（持久化 profile + 登入偵測純函式）

**Files:**
- Create: `sentinel/src/career_sentinel/browser.py`
- Test: `sentinel/tests/test_browser.py`

**Interfaces:**
- Consumes: `config.profile_dir`。
- Produces：
  - `is_login_url(url: str) -> bool`（純函式，可單測：判斷是否被導到登入頁）
  - `LOGGED_IN_PROBE_URL: str`（登入後才看得到的頁；spike 可校正）
  - `open_context(p)`（`launch_persistent_context`，回 context；需真瀏覽器，不單測）
  - `ensure_logged_in(page) -> bool`（goto 探針頁，依 `is_login_url` 判定；需真瀏覽器，不單測）

**註：** `open_context` / `ensure_logged_in` 依賴真實 Playwright，本任務只對純函式 `is_login_url` 寫單測；整合行為由 Task 11 spike 實機驗證。

- [ ] **Step 1: 寫失敗測試 `tests/test_browser.py`**

```python
from career_sentinel import browser


def test_is_login_url_detects_login_page():
    assert browser.is_login_url("https://www.104.com.tw/login") is True
    assert browser.is_login_url("https://account.104.com.tw/login?return=...") is True


def test_is_login_url_false_for_logged_in_page():
    assert browser.is_login_url("https://www.104.com.tw/jobs/apply/analytics") is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_browser.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `browser.py`**

```python
from __future__ import annotations

from . import config

# 登入後才看得到的探針頁（spike 時校正成穩定的私人頁）
LOGGED_IN_PROBE_URL = "https://www.104.com.tw/my/apply"


def is_login_url(url: str) -> bool:
    return "/login" in url or "account.104.com.tw" in url


def open_context(p):
    """launch_persistent_context：用專用 profile 開真 Chrome。需先 `playwright install chromium`。"""
    config.profile_dir().mkdir(parents=True, exist_ok=True)
    return p.chromium.launch_persistent_context(
        user_data_dir=str(config.profile_dir()),
        headless=False,
        channel="chrome",
    )


def ensure_logged_in(page) -> bool:
    page.goto(LOGGED_IN_PROBE_URL, wait_until="domcontentloaded")
    return not is_login_url(page.url)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_browser.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/browser.py sentinel/tests/test_browser.py
git commit -m "feat(sentinel): 瀏覽器登入殼（持久化 profile + 登入偵測）"
```

---

### Task 9: CLI（login / run，run 串接整條管線跑假資料）

**Files:**
- Create: `sentinel/src/career_sentinel/cli.py`
- Test: `sentinel/tests/test_cli.py`

**Interfaces:**
- Consumes: `store`、`diff`、`digest`、`scraper.fake`、`config`、`browser`。
- Produces：
  - `run_pipeline(scrape, conn, *, now: str) -> str`（純協調：scrape→存→diff→彙整→回報告字串，可注入假 scrape/conn 單測）
  - `main(argv=None) -> int`（argparse：`login` / `run`）

**設計：** `run_pipeline` 不直接碰瀏覽器（吃一個 `scrape` callable），故可用 `fake.scrape` 與臨時 DB 單測。`main` 的 `run` 子命令把真 `browser` + Phase 2 真爬蟲接上（本階段先接 `fake.scrape`）。

- [ ] **Step 1: 寫失敗測試 `tests/test_cli.py`**

```python
from career_sentinel import cli, store
from career_sentinel.scraper import fake


def test_run_pipeline_first_run_reports_changes(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    report = cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")
    assert "台積電" in report
    assert store.latest_two_ids(conn)  # 有寫入快照


def test_run_pipeline_second_identical_run_reports_no_change(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")
    report = cli.run_pipeline(fake.scrape, conn, now="2026-06-29T10:00:00")
    assert "沒有新變化" in report


def test_main_unknown_command_returns_nonzero():
    assert cli.main(["bogus"]) != 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_cli.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `cli.py`**

```python
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Callable

from . import browser, config, diff, digest, store
from .models import Snapshot
from .scraper import fake


def run_pipeline(scrape: Callable[[], Snapshot], conn, *, now: str) -> str:
    snapshot = scrape()
    sid = store.save_snapshot(conn, snapshot, run_at=now)
    d = diff.diff_against_last(conn, sid)
    return digest.summarize(d, snapshot)


def _cmd_login() -> int:
    from playwright.sync_api import sync_playwright

    print("開啟 Chrome，請在視窗內登入 104（含驗證碼）。登入完成後關閉視窗即可。")
    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.104.com.tw/", wait_until="domcontentloaded")
        input("登入完成後按 Enter 關閉…")
        ctx.close()
    return 0


def _cmd_run() -> int:
    from playwright.sync_api import sync_playwright

    conn = store.connect(config.db_path())
    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not browser.ensure_logged_in(page):
            ctx.close()
            print("尚未登入，請先執行：career-sentinel login")
            return 1
        ctx.close()
    # Phase 1：先用假爬蟲；Phase 2 改成真爬蟲 scraper.scrape(page)
    report = run_pipeline(fake.scrape, conn, now=datetime.now().isoformat(timespec="seconds"))
    print(report)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="career-sentinel")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("login", help="首次：開 Chrome 手動登入 104")
    sub.add_parser("run", help="擷取 → 比對 → 彙整")
    args = parser.parse_args(argv)
    if args.cmd == "login":
        return _cmd_login()
    if args.cmd == "run":
        return _cmd_run()
    parser.print_help()
    return 2
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_cli.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/cli.py sentinel/tests/test_cli.py
git commit -m "feat(sentinel): CLI（login/run）+ run_pipeline 串接整條管線"
```

---

### Task 10: 全測試綠 + 端到端假資料 run 驗證

**Files:**
- Modify: 無（驗證任務）

- [ ] **Step 1: 跑全部測試**

Run: `cd sentinel && uv run pytest -v`
Expected: 全 PASS（Task 1–9 所有測試）。

- [ ] **Step 2: 端到端 run（假爬蟲，免登入路徑驗證管線）**

為了不依賴真 104，臨時用 Python 直接跑 `run_pipeline`：

Run:
```bash
cd sentinel && uv run python -c "from career_sentinel import cli, store; import tempfile, os; db=os.path.join(tempfile.mkdtemp(),'d.sqlite'); from career_sentinel.scraper import fake; c=store.connect(db); print(cli.run_pipeline(fake.scrape, c, now='2026-06-28T10:00:00'))"
```
Expected: 印出含「台積電」「邀請面試」「面試邀約」等字樣的彙整文字（無 LLM key 時走本地後援）。

- [ ] **Step 3: Commit（若有微調）**

```bash
git add -A sentinel
git commit -m "test(sentinel): Phase 1 全測試綠 + 端到端假資料管線驗證" --allow-empty
```

---

### Task 11: Spike — 擷取真 104 三類資料回應，存成 fixture（Phase 2 前置）

**Files:**
- Create: `sentinel/spike/capture_104.py`（一次性探查腳本，非正式模組）
- Create: `sentinel/tests/fixtures/`（存擷取到的真實回應 JSON/HTML）
- Create: `sentinel/spike/FINDINGS.md`（記錄三類資料各自的 URL、回應結構、欄位對應）

**這是調查任務（手動、無法單元測）。** 目標：實機確認登入流程、摸出三類資料的 XHR 端點與回應結構，產出 fixture 與欄位對應文件，供 Phase 2 寫真爬蟲。

- [ ] **Step 1: 安裝 Playwright 瀏覽器**

Run: `cd sentinel && uv run playwright install chromium`
Expected: 下載完成無錯。

- [ ] **Step 2: 首次登入**

Run: `cd sentinel && uv run career-sentinel login`
Expected: 開出 Chrome，手動登入 104 成功；關閉後 `data/chrome-profile/` 產生。

- [ ] **Step 3: 寫擷取腳本 `sentinel/spike/capture_104.py`**

```python
"""一次性探查：開已登入 Chrome，攔截各私人頁面的 XHR 回應並存檔。
用法：uv run python spike/capture_104.py
逐一造訪「誰看過我 / 我的應徵 / 訊息中心」頁，把 response（JSON 優先）dump 到 tests/fixtures/。
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from career_sentinel import browser

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

# spike 時把真實私人頁網址填進來（從瀏覽器網址列複製）
PAGES = {
    "viewers": "https://www.104.com.tw/...",       # 誰看過我
    "applications": "https://www.104.com.tw/...",  # 我的應徵
    "messages": "https://www.104.com.tw/...",      # 訊息中心
}


def main():
    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for name, url in PAGES.items():
            captured: list = []

            def on_response(r):
                ct = r.headers.get("content-type", "")
                if "/api" in r.url or ct.startswith("application/json"):
                    captured.append(r)

            page.on("response", on_response)
            page.goto(url, wait_until="networkidle")
            page.remove_listener("response", on_response)
            for i, r in enumerate(captured):
                try:
                    body = r.json()
                except Exception:
                    continue
                (OUT / f"{name}_{i}.json").write_text(
                    json.dumps({"url": r.url, "body": body}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
        ctx.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑擷取、檢視回應、挑出正確端點**

Run: `cd sentinel && uv run python spike/capture_104.py`
然後人工檢視 `tests/fixtures/*.json`，找出三類資料各自「真正帶資料」的那個回應，刪掉雜訊檔，將正確的重新命名為 `viewers.json` / `applications.json` / `messages.json`。

- [ ] **Step 5: 記錄發現 `sentinel/spike/FINDINGS.md`**

把三類資料各自的：真實 URL、HTTP 方法、回應 JSON 路徑（哪個欄位是公司/職稱/狀態/時間/thread/邀約）寫下來，作為 Phase 2 解析函式的依據。若某頁是 server-render（無 JSON），記為「需 DOM」並貼上關鍵選擇器。

- [ ] **Step 6: Commit（fixture + findings；勿提交 profile 或個資過多的原始檔）**

先確認 `data/` 已被 `.gitignore` 忽略；fixture 若含個資，斟酌去識別化或只留結構。

```bash
git add sentinel/spike/FINDINGS.md sentinel/tests/fixtures
git commit -m "spike(sentinel): 擷取 104 三類資料真實回應 + 端點/欄位對應發現"
```

---

## Phase 1 完成後

此時你有：一條測試全綠、端到端跑得通（假資料）的管線，且已用 spike 摸清真 104 三類資料的端點與結構。

**Phase 2（另開計畫）**：依 `spike/FINDINGS.md` 的 fixture 與欄位對應，TDD 寫三個真解析函式
（`scraper/viewers.py`、`applications.py`、`messages.py`，各含「攔截抓取」與「純解析」），
組成 `scraper.scrape(page) -> Snapshot`，在 `cli._cmd_run` 把 `fake.scrape` 換成 `scraper.scrape(page)`，實機驗證。

> **ctx 順序**：Phase 1 的 `_cmd_run` 在跑 pipeline 前就 `ctx.close()`（因 `fake.scrape()` 不吃 page）。
> Phase 2 的 `scraper.scrape(page)` 需要 page，務必把 pipeline 呼叫**移進** `with sync_playwright()` 區塊、
> 在 `ctx.close()` 之前（cli.py 已留註解標記此處）。

> **per-reader 容錯（最終 review Important #2，務必在 Phase 2 一併處理，否則會變 schema 改造）**：
> 目前 `Snapshot` 無法區分「viewers 真的是空」與「viewer 讀取器失敗」。Phase 2 真爬蟲若對單一讀取器
> 失敗只回空清單，`save_snapshot` 會存進空資料，下次 `compute_diff` 會把該類全部重新標記為「新」、
> 污染 baseline（spec 明文禁止「失敗的讀取器寫該類空資料」）。**Phase 2 應一併**：
> 1. 在 `Snapshot` 加 per-category 完成訊號（如 `failed_readers: set[str]` 或各類 `*_ok: bool`），並持久化到 `snapshots` 表；
> 2. `diff_against_last` 改為**逐類**挑「最近一次成功讀到該類」的快照當該類 baseline（而非整筆最近快照）；
> 3. 真爬蟲對每個讀取器 try/except，失敗者標記 failed、不寫空資料。

後續子專案（各自 spec→plan）：每日彙整報告強化 → 行事曆整合（面試邀約自動進 Google Calendar）→ 對話式履歷整理。
