# career-sentinel SP2 — 設定 + 關注清單 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 SP1 web app 上加設定頁（關注公司/職缺關鍵字/通知時間，本地持久化）與儀表板即時「★關注」標記。

**Architecture:** 新增 `models.Settings`（含 notify_time 驗證）、`store` 的 settings 表 + load/save、純函式模組 `watch.is_watched`；`web/app.py` 加 `GET/PUT /api/settings` 並讓 `/api/snapshot` 每 item 多 `watched` 旗標；前端加設定 Modal + 關注徽章。

**Tech Stack:** Python 3.12+、Pydantic v2、FastAPI、SQLite、React+Vite+Mantine+TanStack Query。

## Global Constraints

- `sentinel/` 獨立，**不 import/依賴** 雲端 `backend/`、`frontend/`；套件名 `career_sentinel`。
- `is_watched`：關注公司為 item 公司的**不分大小寫子字串**、關鍵字**不分大小寫出現在 haystack**；strip 後空白項忽略；兩清單皆空 → False。haystack：viewer=job_title、application=title、message=last_message。
- `notify_time`：None 或符合 `^([01]\d|2[0-3]):[0-5]\d$`；PUT 不合 → HTTP 422。
- `/api/snapshot` 只**新增** 每 item 的 `watched` 欄位，其餘形狀與 SP1 相同。
- 後端只綁 127.0.0.1（沿用 SP1）。
- 驗證閘門：`cd sentinel && uv run pytest` 全綠；`cd sentinel/web/frontend && npm run build` 成功。
- Phase 1/2/SP1 既有測試不得回歸。

---

### Task 1: `Settings` 模型 + store settings 表

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`
- Modify: `sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_settings_store.py`

**Interfaces:**
- Produces：
  - `models.Settings(watched_companies: list[str], watched_keywords: list[str], notify_time: str | None)`，notify_time 驗證 HH:MM
  - `store.load_settings(conn) -> Settings`、`store.save_settings(conn, settings: Settings) -> None`

- [ ] **Step 1: 寫失敗測試 `tests/test_settings_store.py`**

```python
import pytest
from pydantic import ValidationError

from career_sentinel import store
from career_sentinel.models import Settings


def test_settings_defaults():
    s = Settings()
    assert s.watched_companies == [] and s.watched_keywords == [] and s.notify_time is None


def test_settings_rejects_bad_time():
    with pytest.raises(ValidationError):
        Settings(notify_time="25:99")


def test_settings_accepts_good_time_and_none():
    assert Settings(notify_time="09:30").notify_time == "09:30"
    assert Settings(notify_time=None).notify_time is None


def test_load_settings_default_when_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    s = store.load_settings(conn)
    assert s == Settings()


def test_save_and_load_settings_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_settings(conn, Settings(watched_companies=["台積電"], watched_keywords=["後端"], notify_time="09:00"))
    s = store.load_settings(conn)
    assert s.watched_companies == ["台積電"]
    assert s.watched_keywords == ["後端"]
    assert s.notify_time == "09:00"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_settings_store.py -v`
Expected: FAIL（`ImportError: cannot import name 'Settings'` 或 `AttributeError`）。

- [ ] **Step 3: 在 `models.py` 加 `Settings`**

在 `models.py` 頂端 import 區補上 `re` 與 `field_validator`（`from pydantic import BaseModel, Field, field_validator`；`import re`），並在檔案末尾加入：

```python
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Settings(BaseModel):
    watched_companies: list[str] = Field(default_factory=list)
    watched_keywords: list[str] = Field(default_factory=list)
    notify_time: str | None = None

    @field_validator("notify_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_RE.match(v):
            raise ValueError("notify_time 需為 HH:MM")
        return v
```

- [ ] **Step 4: 在 `store.py` 加 settings 表與 load/save**

把 `store.py` 頂端 `from .models import Application, Message, Snapshot, Viewer` 改為加入 `Settings`：
```python
from .models import Application, Message, Settings, Snapshot, Viewer
```

在 `_SCHEMA` 字串末尾（最後一個 `CREATE TABLE` 之後、結尾 `"""` 之前）加一行：
```sql
CREATE TABLE IF NOT EXISTS settings (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
```

在 `store.py` 末尾加：
```python
def load_settings(conn: sqlite3.Connection) -> Settings:
    row = conn.execute("SELECT data FROM settings WHERE id = 1").fetchone()
    if not row:
        return Settings()
    return Settings.model_validate_json(row[0])


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (id, data) VALUES (1, ?)",
        (settings.model_dump_json(),),
    )
    conn.commit()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_settings_store.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 6: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS（既有快照表測試不受新 settings 表影響）。

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_settings_store.py
git commit -m "feat(sentinel): Settings 模型(含 HH:MM 驗證) + store settings 表 load/save"
```

---

### Task 2: `watch.is_watched` 純函式

**Files:**
- Create: `sentinel/src/career_sentinel/watch.py`
- Test: `sentinel/tests/test_watch.py`

**Interfaces:**
- Consumes：`models.Settings`。
- Produces：`watch.is_watched(company: str, haystack: str, settings: Settings) -> bool`。

- [ ] **Step 1: 寫失敗測試 `tests/test_watch.py`**

```python
from career_sentinel.models import Settings
from career_sentinel.watch import is_watched


def test_company_substring_match():
    assert is_watched("台積電股份有限公司", "後端工程師", Settings(watched_companies=["台積電"])) is True


def test_keyword_match_in_haystack():
    assert is_watched("某公司", "資深後端工程師", Settings(watched_keywords=["後端"])) is True


def test_case_insensitive():
    assert is_watched("X", "Senior BACKEND Engineer", Settings(watched_keywords=["backend"])) is True


def test_blank_entries_ignored():
    assert is_watched("台積電", "後端", Settings(watched_companies=["  "], watched_keywords=[""])) is False


def test_empty_settings_false():
    assert is_watched("台積電", "後端", Settings()) is False


def test_no_match():
    assert is_watched("台積電", "後端工程師", Settings(watched_companies=["聯發科"], watched_keywords=["前端"])) is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_watch.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `watch.py`**

```python
from __future__ import annotations

from .models import Settings


def is_watched(company: str, haystack: str, settings: Settings) -> bool:
    """命中任一關注公司（為 company 的不分大小寫子字串）或任一關鍵字（出現在 haystack）。"""
    company_l = (company or "").lower()
    for raw in settings.watched_companies:
        term = raw.strip().lower()
        if term and term in company_l:
            return True
    hay_l = (haystack or "").lower()
    for raw in settings.watched_keywords:
        term = raw.strip().lower()
        if term and term in hay_l:
            return True
    return False
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_watch.py -v`
Expected: PASS（6 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/watch.py sentinel/tests/test_watch.py
git commit -m "feat(sentinel): watch.is_watched（關注公司子字串/關鍵字比對，純函式）"
```

---

### Task 3: API `GET/PUT /api/settings` + snapshot `watched` 旗標

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_settings.py`

**Interfaces:**
- Consumes：`store.{load_settings,save_settings}`、`watch.is_watched`、`models.Settings`。
- Produces：`GET /api/settings`、`PUT /api/settings`（壞 notify_time→422）、`/api/snapshot` 每 item 加 `watched`。

- [ ] **Step 1: 寫失敗測試 `tests/test_web_settings.py`**

```python
from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel import store
from career_sentinel.models import Snapshot, Viewer


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_get_settings_default(tmp_path):
    body = _client(tmp_path).get("/api/settings").json()
    assert body["watched_companies"] == []
    assert body["watched_keywords"] == []
    assert body["notify_time"] is None


def test_put_and_get_settings_roundtrip(tmp_path):
    c = _client(tmp_path)
    r = c.put("/api/settings", json={"watched_companies": ["台積電"], "watched_keywords": ["後端"], "notify_time": "09:30"})
    assert r.status_code == 200
    body = c.get("/api/settings").json()
    assert body["watched_companies"] == ["台積電"]
    assert body["notify_time"] == "09:30"


def test_put_settings_invalid_time_422(tmp_path):
    r = _client(tmp_path).put("/api/settings", json={"watched_companies": [], "watched_keywords": [], "notify_time": "25:99"})
    assert r.status_code == 422


def test_snapshot_includes_watched_flag(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(
        viewers=[Viewer(company="台積電股份有限公司", job_title="後端", viewed_at="t")],
    ), run_at="2026-06-29T10:00:00")
    c = _client(tmp_path)
    c.put("/api/settings", json={"watched_companies": ["台積電"], "watched_keywords": [], "notify_time": None})
    body = c.get("/api/snapshot").json()
    assert body["viewers"][0]["watched"] is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_settings.py -v`
Expected: FAIL（404 settings 端點不存在 / snapshot 無 watched 欄位）。

- [ ] **Step 3: 改 `web/app.py`**

把 `app.py` 頂端 import 區補上 `watch` 與 `Settings`：
```python
from .. import config, diff, digest, store, watch
from ..models import Settings
from . import runner
```

把 `_snapshot_payload` 的非空分支改為先載設定、每 item 加 `watched`（整個函式替換為）：
```python
def _snapshot_payload(conn) -> dict:
    failed = runner.status()["last_failed_readers"]
    ids = store.latest_two_ids(conn)
    if not ids:
        return {
            "run_at": None,
            "viewers": [], "applications": [], "messages": [],
            "digest": "尚無資料，請先重新抓取",
            "failed_readers": failed,
        }
    sid = ids[0]
    snap = store.load_snapshot(conn, sid)
    d = diff.diff_against_last(conn, sid)
    settings = store.load_settings(conn)
    return {
        "run_at": store.latest_run_at(conn),
        "viewers": [{"company": v.company, "job_title": v.job_title, "viewed_at": v.viewed_at, "watched": watch.is_watched(v.company, v.job_title, settings)} for v in snap.viewers],
        "applications": [{"job_id": a.job_id, "company": a.company, "title": a.title, "status": a.status, "applied_at": a.applied_at, "watched": watch.is_watched(a.company, a.title, settings)} for a in snap.applications],
        "messages": [{"thread_id": m.thread_id, "company": m.company, "last_message": m.last_message, "has_interview_invite": m.has_interview_invite, "watched": watch.is_watched(m.company, m.last_message, settings)} for m in snap.messages],
        "digest": digest.render_human(d, snap),
        "failed_readers": failed,
    }
```

在 `create_app` 內、`GET /api/status` 路由之後（`return app` 之前、靜態掛載之前）加兩個設定端點：
```python
    @app.get("/api/settings")
    def get_settings() -> dict:
        return store.load_settings(_conn()).model_dump()

    @app.put("/api/settings")
    def put_settings(settings: Settings) -> dict:
        store.save_settings(_conn(), settings)
        return settings.model_dump()
```

（`put_settings` 的 body 型別是 `Settings`，FastAPI 會用 Pydantic 驗證——壞 `notify_time` 自動回 422。）

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_web_settings.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 跑全測試確認無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS（既有 test_web_app 的 snapshot 測試不檢查 watched，仍通過）。

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_settings.py
git commit -m "feat(sentinel): /api/settings GET·PUT + snapshot 每 item 加 watched 旗標"
```

---

### Task 4: 前端設定 Modal + 關注徽章

**Files:**
- Create: `sentinel/web/frontend/src/SettingsModal.tsx`
- Modify: `sentinel/web/frontend/src/api.ts`
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`

**Interfaces:**
- Consumes：後端 `/api/settings`（GET/PUT）、`/api/snapshot` 的 `watched`。
- Produces：可 build 的儀表板，含設定 Modal 與 ★關注 徽章。

- [ ] **Step 1: 改 `src/api.ts`（加 watched 欄位 + Settings 型別與函式）**

在 `Viewer`、`Application`、`Message` 三個 interface 各加一行 `watched: boolean;`：
```ts
export interface Viewer { company: string; job_title: string; viewed_at: string; watched: boolean }
export interface Application { job_id: string; company: string; title: string; status: string; applied_at: string; watched: boolean }
export interface Message { thread_id: string; company: string; last_message: string; has_interview_invite: boolean; watched: boolean }
```

在 `api.ts` 末尾加 Settings 型別與函式：
```ts
export interface Settings { watched_companies: string[]; watched_keywords: string[]; notify_time: string | null }

export async function getSettings(): Promise<Settings> {
  const r = await fetch("/api/settings");
  return r.json();
}

export async function putSettings(s: Settings): Promise<Response> {
  return fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(s),
  });
}
```

- [ ] **Step 2: 建立 `src/SettingsModal.tsx`**

```tsx
import { Button, Modal, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getSettings, putSettings, type Settings } from "./api";

export default function SettingsModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings, enabled: opened });
  const [companies, setCompanies] = useState("");
  const [keywords, setKeywords] = useState("");
  const [notifyTime, setNotifyTime] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (settings.data) {
      setCompanies(settings.data.watched_companies.join("\n"));
      setKeywords(settings.data.watched_keywords.join("\n"));
      setNotifyTime(settings.data.notify_time ?? "");
    }
  }, [settings.data]);

  async function save() {
    setErr(null);
    const payload: Settings = {
      watched_companies: companies.split("\n").map((s) => s.trim()).filter(Boolean),
      watched_keywords: keywords.split("\n").map((s) => s.trim()).filter(Boolean),
      notify_time: notifyTime.trim() === "" ? null : notifyTime.trim(),
    };
    const r = await putSettings(payload);
    if (!r.ok) { setErr("時間格式需為 HH:MM"); return; }
    qc.invalidateQueries({ queryKey: ["settings"] });
    qc.invalidateQueries({ queryKey: ["snapshot"] });
    onClose();
  }

  return (
    <Modal opened={opened} onClose={onClose} title="設定">
      <Stack>
        <Textarea label="關注公司（一行一個）" autosize minRows={3} value={companies} onChange={(e) => setCompanies(e.currentTarget.value)} />
        <Textarea label="職缺關鍵字（一行一個）" autosize minRows={3} value={keywords} onChange={(e) => setKeywords(e.currentTarget.value)} />
        <TextInput type="time" label="通知時間（HH:MM）" value={notifyTime} onChange={(e) => setNotifyTime(e.currentTarget.value)} />
        {err && <Text c="red" size="sm">{err}</Text>}
        <Button onClick={save}>儲存</Button>
      </Stack>
    </Modal>
  );
}
```

- [ ] **Step 3: 改 `src/Dashboard.tsx`（設定按鈕 + Modal + ★關注 徽章）**

1) 在 import 區加：
```tsx
import SettingsModal from "./SettingsModal";
```

2) 在 `Dashboard()` 元件內、既有 `const [polling, setPolling] = useState(false);` 附近加一個狀態：
```tsx
  const [settingsOpen, setSettingsOpen] = useState(false);
```

3) 在頂部 header 的 `<Group>`（含「重新抓取」按鈕那組）內，於「重新抓取」按鈕**之前**加「設定」按鈕：
```tsx
          <Button variant="default" onClick={() => setSettingsOpen(true)}>設定</Button>
```

4) 在 return 的 JSX 最外層 `<Container>` 內**最後**（三面板 `</Group>` 之後）加入 Modal：
```tsx
      <SettingsModal opened={settingsOpen} onClose={() => setSettingsOpen(false)} />
```

5) 三個面板的每個 item 前面加 ★關注 徽章。把三處 `.map(...)` 的渲染改為在文字前插入：
```tsx
{v.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}
```
對 viewers 用 `v.watched`、applications 用 `a.watched`、messages 用 `m.watched`（messages 的徽章放在既有「面試」徽章之後、公司名之前）。`Badge` 已在 SP1 的 import 內。

- [ ] **Step 4: 建置（閘門）**

Run: `cd sentinel/web/frontend && npm run build`
Expected: `tsc -b && vite build` 無型別錯誤、`✓ built`、產出 `dist/`。

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/SettingsModal.tsx sentinel/web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 前端設定 Modal（關注公司/關鍵字/通知時間）+ ★關注 徽章"
```

---

### Task 5: 真機整合驗證（控制器）

**Files:** 無（驗證任務）

- [ ] **Step 1: 全測試 + 前端建置**

Run: `cd sentinel && uv run pytest -q && cd web/frontend && npm run build`
Expected: pytest 全綠、build 成功。

- [ ] **Step 2: 真機目視（控制器執行）**

`cd sentinel && uv run career-sentinel serve` → 瀏覽器：
- 按「設定」開 Modal，填關注公司（例如某個你已知看過你的公司名片段）+ 通知時間，存。
- Modal 關閉後，儀表板對應 item 出現「★關注」徽章。
- 重開「設定」，剛存的值仍在。
- 填非法時間（如 `99:99`）存 → 顯示「時間格式需為 HH:MM」、不關閉。

- [ ] **Step 3: Commit（如有微調）**

```bash
git add -A sentinel
git commit -m "test(sentinel): SP2 全測試 + 前端建置 + 真機目視驗證" --allow-empty
```

---

## 完成後

`career-sentinel serve` 的儀表板可設定關注清單與通知時間、命中項目即時標「★關注」。接 SP3（履歷健檢）/SP4（JD 比對）/SP5（推薦，使用本 SP 的 `watch.is_watched`）。見路線圖。
