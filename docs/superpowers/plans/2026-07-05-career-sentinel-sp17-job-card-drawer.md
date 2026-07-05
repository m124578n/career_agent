# SP17：職缺連動卡片（Drawer）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 求職中心點開職缺 → 右側 Drawer 卡片把 比對/研究/客製化 串在同一職缺脈絡上、結果每職缺快取進脊椎、完成客製化自動 tag `已客製化`，並把獨立的「客製化」頁摺進卡片。

**Architecture:** `tracked_jobs` 加 `match_json`/`tailor_json` 兩欄存卡片快取（冪等 ALTER 遷移）；抽 `store.merge_tracked_job` 統一 upsert 合併邏輯（去重/取較前面/不降級終端/保留 created_at），SP16 的 `/api/tracked` 與卡片快取共用它。`POST /api/match`/`/api/tailor` 端點**不改**，由前端卡片拿到結果後另呼叫 `POST /api/tracked` 快取＋auto-tag。新 `GET /api/tracked/{code}` 供卡片讀快取；`/api/snapshot` 輸出 `tracked_codes`。前端新增 `JobCardDrawer`，求職中心列可點開，移除 `TailorPage`。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、SQLite、pytest；React 18 ＋ Vite ＋ Mantine 7（Drawer）＋ TanStack Query。

## Global Constraints

- **不改動 `POST /api/match`、`POST /api/tailor` 的行為與回傳**：卡片在前端拿到結果後另呼叫 `POST /api/tracked` 快取，不讓 FindJobsPage 的 inline 比對變成自動追蹤（SP16「比對≠追蹤」不變）。
- **快取/auto-tag 純本地寫入，不碰 104**：只 `POST /api/tracked`（本地 SQLite）；研究沿用既有 `company_research` 快取。
- **加法式遷移不炸既有 DB**：`tracked_jobs` 兩新欄用 `PRAGMA table_info` 檢查後冪等 `ALTER TABLE ADD COLUMN`；新 DB 由 `_SCHEMA` 直接含欄。
- **auto-tag 不降級**：客製化→`tailored`、比對→`matched`，經 `merge_tracked_job` 與既有 state 取較前面、不覆蓋既有終端 `offer`/`rejected`。
- **不得弄丟 SP7 面試功能與 SP15/16 既有管道**：Dashboard 只加「列可點開 Drawer」，既有列內按鈕（gcal/dismiss-restore/取消追蹤/研究）行為不變、用 `stopPropagation` 不誤觸卡片。
- **相容**：`/api/snapshot` 只新增 `tracked_codes`；`POST /api/tracked` 擴充向後相容（新欄選填）；search/recommend/match/tailor/apply 回傳不變。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 `127.0.0.1`；前端 `npm run build`（noUnusedLocals）必過。
- 測試：後端 `cd sentinel && ./.venv/Scripts/python.exe -m pytest`；前端 `cd sentinel/web/frontend && npm run build`。

---

### Task 1: tracked_jobs 兩新欄 ＋ 遷移 ＋ merge_tracked_job

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（`TrackedJob` 加 `match_json`/`tailor_json`）
- Modify: `sentinel/src/career_sentinel/store.py`（schema 兩欄、`_migrate`、load/get/upsert 兩欄、新 `merge_tracked_job`；補 `datetime` import）
- Test: `sentinel/tests/test_merge_tracked.py`（新檔）

**Interfaces:**
- Consumes（既有）：`pipeline.STATE_RANK`/`pipeline.TERMINAL`（延遲 import 避免循環）、`models.TrackedJob`、`store.get_tracked_job`/`upsert_tracked_job`。
- Produces：
  - `models.TrackedJob` 新增 `match_json: str = ""`、`tailor_json: str = ""`
  - `store.merge_tracked_job(conn, code: str, *, state: str|None=None, match_score: int|None=None, match_json: dict|None=None, tailor_json: dict|None=None, company: str="", title: str="", url: str="", salary: str="") -> str`（回最終 state）

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_merge_tracked.py`：

```python
import json
from career_sentinel import store
from career_sentinel.models import TrackedJob


def test_columns_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="a1", match_json='{"score":80}', tailor_json='{"x":1}'))
    j = store.get_tracked_job(conn, "a1")
    assert j.match_json == '{"score":80}' and j.tailor_json == '{"x":1}'


def test_old_db_gains_columns(tmp_path):
    # 模擬缺兩欄的舊 schema：先手動建一張沒有 match_json/tailor_json 的 tracked_jobs
    import sqlite3
    p = tmp_path / "db.sqlite"
    c = sqlite3.connect(str(p))
    c.execute("CREATE TABLE tracked_jobs (code TEXT PRIMARY KEY, company TEXT, title TEXT, url TEXT, "
              "salary TEXT, state TEXT, match_score INTEGER, created_at TEXT, updated_at TEXT)")
    c.execute("INSERT INTO tracked_jobs (code, state) VALUES ('old1','interested')")
    c.commit(); c.close()
    conn = store.connect(p)  # connect 應冪等 ALTER 補欄
    j = store.get_tracked_job(conn, "old1")
    assert j is not None and j.match_json == "" and j.tailor_json == ""


def test_merge_new_job_defaults_interested(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    final = store.merge_tracked_job(conn, "a1", company="甲", title="後端")
    assert final == "interested"
    assert store.get_tracked_job(conn, "a1").company == "甲"


def test_merge_matched_stores_match_json(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    final = store.merge_tracked_job(conn, "a1", state="matched", match_score=88,
                                    match_json={"score": 88, "reasons": ["r1"]})
    assert final == "matched"
    j = store.get_tracked_job(conn, "a1")
    assert j.match_score == 88
    assert json.loads(j.match_json)["reasons"] == ["r1"]


def test_merge_tailored_stores_tailor_json(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    final = store.merge_tracked_job(conn, "a1", state="tailored",
                                    tailor_json={"cover_letter": "您好"})
    assert final == "tailored"
    assert json.loads(store.get_tracked_job(conn, "a1").tailor_json)["cover_letter"] == "您好"


def test_merge_keeps_created_at_and_furthest(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="a1", state="matched", match_score=80,
                                              created_at="2026-07-01T00:00:00"))
    store.merge_tracked_job(conn, "a1", state="interested")  # 較後面，應維持 matched
    j = store.get_tracked_job(conn, "a1")
    assert j.state == "matched" and j.created_at == "2026-07-01T00:00:00"


def test_merge_does_not_downgrade_terminal(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="a1", state="offer", created_at="2026-07-01T00:00:00"))
    store.merge_tracked_job(conn, "a1", state="tailored", tailor_json={"cover_letter": "x"})
    j = store.get_tracked_job(conn, "a1")
    assert j.state == "offer"  # 不降級
    assert json.loads(j.tailor_json)["cover_letter"] == "x"  # 但快取仍寫入


def test_merge_keeps_old_json_when_not_provided(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.merge_tracked_job(conn, "a1", state="matched", match_score=80, match_json={"score": 80})
    store.merge_tracked_job(conn, "a1", state="tailored", tailor_json={"cover_letter": "y"})
    j = store.get_tracked_job(conn, "a1")
    assert json.loads(j.match_json)["score"] == 80  # match_json 未帶時保留
    assert json.loads(j.tailor_json)["cover_letter"] == "y"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_merge_tracked.py -v`
Expected: FAIL（`TypeError`/`AttributeError`：`merge_tracked_job` 不存在、model 無 match_json）

- [ ] **Step 3: models 加兩欄**

`sentinel/src/career_sentinel/models.py` 的 `TrackedJob` 加兩個欄位（放在 `match_score` 之後）：

```python
    match_json: str = ""
    tailor_json: str = ""
```

- [ ] **Step 4: store schema/遷移/欄位/merge**

`sentinel/src/career_sentinel/store.py`：

(a) 頂部 import 補 `from datetime import datetime`（若尚未 import）。

(b) `_SCHEMA` 內 `CREATE TABLE IF NOT EXISTS tracked_jobs (...)` 的欄位清單，在 `updated_at` 之後加：
```sql
    match_json TEXT NOT NULL DEFAULT '',
    tailor_json TEXT NOT NULL DEFAULT ''
```

(c) `connect()` 在 `conn.executescript(_SCHEMA)` 之後、`return conn` 之前插入 `_migrate(conn)`；並新增 `_migrate`：

```python
def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tracked_jobs)")}
    for col in ("match_json", "tailor_json"):
        if col not in cols:
            conn.execute(f"ALTER TABLE tracked_jobs ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    conn.commit()
```

(d) `load_tracked_jobs` 與 `get_tracked_job` 的 SELECT 欄位補 `match_json, tailor_json`、unpack 與 `TrackedJob(...)` 建構補這兩欄；`upsert_tracked_job` 的 INSERT 欄位與 VALUES 補這兩欄。完整改寫這三個函式：

```python
def load_tracked_jobs(conn: sqlite3.Connection) -> list[TrackedJob]:
    rows = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json FROM tracked_jobs ORDER BY updated_at DESC"
    )
    return [
        TrackedJob(
            code=c, company=co, title=t, url=u, salary=sa, state=st,
            match_score=ms, created_at=ca, updated_at=ua, match_json=mj, tailor_json=tj,
        )
        for c, co, t, u, sa, st, ms, ca, ua, mj, tj in rows
    ]


def get_tracked_job(conn: sqlite3.Connection, code: str) -> TrackedJob | None:
    row = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json FROM tracked_jobs WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        return None
    c, co, t, u, sa, st, ms, ca, ua, mj, tj = row
    return TrackedJob(
        code=c, company=co, title=t, url=u, salary=sa, state=st,
        match_score=ms, created_at=ca, updated_at=ua, match_json=mj, tailor_json=tj,
    )


def upsert_tracked_job(conn: sqlite3.Connection, job: TrackedJob) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_jobs "
        "(code, company, title, url, salary, state, match_score, created_at, updated_at, match_json, tailor_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (job.code, job.company, job.title, job.url, job.salary, job.state,
         job.match_score, job.created_at, job.updated_at, job.match_json, job.tailor_json),
    )
    conn.commit()
```

(e) 檔案結尾新增 `merge_tracked_job`：

```python
def merge_tracked_job(
    conn: sqlite3.Connection, code: str, *,
    state: str | None = None, match_score: int | None = None,
    match_json: dict | None = None, tailor_json: dict | None = None,
    company: str = "", title: str = "", url: str = "", salary: str = "",
) -> str:
    """合併 upsert 一筆追蹤職缺：保留 created_at、取較前面狀態、不降級終端、未帶欄位保留舊值。
    match_json/tailor_json 傳 dict 會序列化存入；回最終 state。"""
    from . import pipeline  # 延遲 import 避免與 pipeline 循環
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_tracked_job(conn, code)
    if existing is not None:
        created_at = existing.created_at or now
        if existing.state in pipeline.TERMINAL:
            final_state = existing.state
        elif state is not None and pipeline.STATE_RANK.get(state, 0) >= pipeline.STATE_RANK.get(existing.state, 0):
            final_state = state
        else:
            final_state = existing.state
        new_score = match_score if match_score is not None else existing.match_score
        new_mj = json.dumps(match_json, ensure_ascii=False) if match_json is not None else existing.match_json
        new_tj = json.dumps(tailor_json, ensure_ascii=False) if tailor_json is not None else existing.tailor_json
        new_co, new_t, new_u, new_sa = (company or existing.company, title or existing.title,
                                        url or existing.url, salary or existing.salary)
    else:
        created_at = now
        final_state = state or "interested"
        new_score = match_score
        new_mj = json.dumps(match_json, ensure_ascii=False) if match_json is not None else ""
        new_tj = json.dumps(tailor_json, ensure_ascii=False) if tailor_json is not None else ""
        new_co, new_t, new_u, new_sa = company, title, url, salary
    upsert_tracked_job(conn, TrackedJob(
        code=code, company=new_co, title=new_t, url=new_u, salary=new_sa,
        state=final_state, match_score=new_score, created_at=created_at, updated_at=now,
        match_json=new_mj, tailor_json=new_tj,
    ))
    return final_state
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_merge_tracked.py -v`
Expected: PASS（8 passed）

- [ ] **Step 6: 全測試回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（既有 tracked/pipeline 測試不受影響）

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_merge_tracked.py
git commit -m "feat(sentinel): tracked_jobs match_json/tailor_json 欄 + 遷移 + merge_tracked_job（SP17）"
```

---

### Task 2: API — /api/tracked 存 JSON、GET /api/tracked/{code}、snapshot tracked_codes

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`（`_TrackReq` 兩欄、`track_job` 改用 merge、新 `GET /api/tracked/{code}`、`_snapshot_payload` 加 `tracked_codes`）
- Test: `sentinel/tests/test_web_card.py`（新檔）

**Interfaces:**
- Consumes：`store.merge_tracked_job`（Task 1）、`store.get_tracked_job`/`load_tracked_jobs`。
- Produces：
  - `POST /api/tracked` 接受選填 `match_json: dict|None`、`tailor_json: dict|None`
  - `GET /api/tracked/{code}` → `{code, found: bool, state, match_score, match: dict|None, tailor: dict|None}`
  - `/api/snapshot` 多 `tracked_codes: list[str]`

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_web_card.py`：

```python
from fastapi.testclient import TestClient
from career_sentinel import store
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_track_with_match_json_stores_and_matched(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "a1", "company": "甲", "title": "後端",
                                     "match_score": 88, "match_json": {"score": 88, "reasons": ["r1"], "gaps": []}})
    assert r.json()["state"] == "matched"
    got = c.get("/api/tracked/a1").json()
    assert got["found"] is True and got["match"]["reasons"] == ["r1"] and got["tailor"] is None


def test_track_with_tailor_json_sets_tailored(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "a1", "tailor_json": {"cover_letter": "您好"}})
    assert r.json()["state"] == "tailored"
    got = c.get("/api/tracked/a1").json()
    assert got["tailor"]["cover_letter"] == "您好"


def test_get_tracked_not_found(tmp_path):
    got = _client(tmp_path).get("/api/tracked/nope").json()
    assert got["found"] is False and got["match"] is None and got["tailor"] is None


def test_track_json_preserved_across_calls(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "a1", "match_score": 80, "match_json": {"score": 80}})
    c.post("/api/tracked", json={"code": "a1", "tailor_json": {"cover_letter": "y"}})
    got = c.get("/api/tracked/a1").json()
    assert got["match"]["score"] == 80 and got["tailor"]["cover_letter"] == "y"


def test_sp16_behavior_unchanged_interested(tmp_path):
    # 無 json / 無 score → interested（SP16 行為回歸）
    c = _client(tmp_path)
    assert c.post("/api/tracked", json={"code": "a1", "title": "後端"}).json()["state"] == "interested"


def test_snapshot_has_tracked_codes(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "a1", "title": "後端"})
    c.post("/api/tracked", json={"code": "b2", "title": "前端"})
    body = c.get("/api/snapshot").json()
    assert set(body["tracked_codes"]) == {"a1", "b2"}


def test_snapshot_empty_tracked_codes(tmp_path):
    body = _client(tmp_path).get("/api/snapshot").json()
    assert body["tracked_codes"] == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_card.py -v`
Expected: FAIL（`KeyError: 'tracked_codes'`、`match_json` 未存、`GET /api/tracked/{code}` 404）

- [ ] **Step 3: `_TrackReq` 加兩欄、`track_job` 改用 merge**

`sentinel/src/career_sentinel/web/app.py`：

(a) `_TrackReq` 加兩個選填欄位（放在 `match_score` 之後）：
```python
    match_json: dict | None = None
    tailor_json: dict | None = None
```

(b) 把既有 `track_job` 端點內文改為呼叫 `store.merge_tracked_job`（移除原本的 inline 合併邏輯）：
```python
    @app.post("/api/tracked")
    def track_job(req: _TrackReq) -> dict:
        if not req.code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        if req.tailor_json is not None:
            state_hint = "tailored"
        elif req.match_json is not None or req.match_score is not None:
            state_hint = "matched"
        else:
            state_hint = "interested"
        final = store.merge_tracked_job(
            _conn(), req.code, state=state_hint,
            match_score=req.match_score, match_json=req.match_json, tailor_json=req.tailor_json,
            company=req.company, title=req.title, url=req.url, salary=req.salary,
        )
        return {"status": "tracked", "state": final}
```

- [ ] **Step 4: 新 `GET /api/tracked/{code}`**

在 `track_job` 附近新增（`json` 已在 app.py import）：
```python
    @app.get("/api/tracked/{code}")
    def tracked_get(code: str) -> dict:
        tj = store.get_tracked_job(_conn(), code)
        if tj is None:
            return {"code": code, "found": False, "state": "", "match_score": None,
                    "match": None, "tailor": None}
        return {
            "code": tj.code, "found": True, "state": tj.state, "match_score": tj.match_score,
            "match": json.loads(tj.match_json) if tj.match_json else None,
            "tailor": json.loads(tj.tailor_json) if tj.tailor_json else None,
        }
```

> 注意：`DELETE /api/tracked/{code}` 已存在；新增的是 `GET`，兩者 path 相同、method 不同，FastAPI 可共存。

- [ ] **Step 5: `_snapshot_payload` 加 `tracked_codes`**

在 `_snapshot_payload` 內，best-effort 算 tracked_codes 並塞進兩個 return dict（比照既有 pipeline 的作法）：
```python
    try:
        tracked_codes = [tj.code for tj in store.load_tracked_jobs(conn)]
    except Exception:
        tracked_codes = []
```
兩個 return dict（空 DB 與有資料）各加一行 `"tracked_codes": tracked_codes,`。

- [ ] **Step 6: 跑測試確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_card.py -v`
Expected: PASS（7 passed）

- [ ] **Step 7: 全測試回歸（含 SP16 的 test_web_tracked.py）**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（SP16 `test_web_tracked.py` 因 track_job 改用 merge 仍須全過）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_card.py
git commit -m "feat(sentinel): /api/tracked 存 match/tailor JSON + GET /api/tracked/{code} + snapshot tracked_codes（SP17）"
```

---

### Task 3: api.ts ＋ JobCardDrawer

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（`SnapshotResp` 加 `tracked_codes`；`TrackReq` 加 `match_json`/`tailor_json`；新 `getTrackedJob`）
- Create: `sentinel/web/frontend/src/JobCardDrawer.tsx`
- 驗證：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：`/api/tracked`（POST，Task 2 擴充）、`GET /api/tracked/{code}`（Task 2）、`POST /api/match`/`/api/tailor`/`/api/apply/open`（既有）。
- Produces（供 Task 4/5）：`getTrackedJob(code): Promise<Response>`；`SnapshotResp.tracked_codes: string[]`；`<JobCardDrawer opened job onClose />`。

- [ ] **Step 1: api.ts 型別與函式**

`sentinel/web/frontend/src/api.ts`：
(a) `SnapshotResp` 加 `tracked_codes: string[];`。
(b) 既有 `TrackReq` interface 加兩欄：
```typescript
  match_json?: unknown;
  tailor_json?: unknown;
```
(c) 新增：
```typescript
export interface TrackedCard {
  code: string;
  found: boolean;
  state: string;
  match_score: number | null;
  match: MatchResult | null;
  tailor: TailoredApplication | null;
}

export async function getTrackedJob(code: string): Promise<Response> {
  return fetch(`/api/tracked/${encodeURIComponent(code)}`);
}
```
（`MatchResult`／`TailoredApplication` 型別已存在於 api.ts。`MatchResult` 需含 `title`/`company`/`salary`——確認既有定義；卡片只用 `score`/`reasons`/`gaps`。）

- [ ] **Step 2: 建立 JobCardDrawer**

建立 `sentinel/web/frontend/src/JobCardDrawer.tsx`：

```tsx
import {
  ActionIcon, Anchor, Badge, Button, Drawer, Group, List, Paper, Progress, Stack, Text, ThemeIcon,
} from "@mantine/core";
import { IconCheck, IconCopy, IconExternalLink } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  getResume, getTrackedJob, matchJob, openApplyPage, tailorApplication, trackJob,
  type MatchResult, type TailoredApplication,
} from "./api";
import BusyHint from "./BusyHint";
import ResearchButton from "./ResearchButton";

export interface CardJob {
  code: string;
  company: string;
  title: string;
  url: string;
  salary: string;
}

export default function JobCardDrawer({ job, opened, onClose }: {
  job: CardJob | null;
  opened: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const canMatch = !!resume.data?.has_resume;
  const hasUrl = !!job?.url;

  const [match, setMatch] = useState<MatchResult | null>(null);
  const [tailor, setTailor] = useState<TailoredApplication | null>(null);
  const [matchBusy, setMatchBusy] = useState(false);
  const [tailorBusy, setTailorBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // 開啟時載入快取
  useEffect(() => {
    if (!opened || !job) return;
    setErr(null); setMatch(null); setTailor(null);
    getTrackedJob(job.code).then((r) => r.json()).then((c) => {
      if (c.match) setMatch(c.match);
      if (c.tailor) setTailor(c.tailor);
    }).catch(() => {});
  }, [opened, job?.code]);

  async function runMatch() {
    if (!job) return;
    setErr(null); setMatchBusy(true);
    try {
      const r = await matchJob(job.url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "比對失敗"); return; }
      setMatch(b);
      const tr = await trackJob({
        code: job.code, company: job.company, title: job.title, url: job.url, salary: job.salary,
        match_score: b.score, match_json: b,
      });
      if (tr.ok) qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setMatchBusy(false); }
  }

  async function runTailor() {
    if (!job) return;
    setErr(null); setTailorBusy(true);
    try {
      const r = await tailorApplication(job.url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "生成失敗"); return; }
      setTailor(b);
      const tr = await trackJob({
        code: job.code, company: job.company, title: job.title, url: job.url, salary: job.salary,
        tailor_json: b,
      });
      if (tr.ok) qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setTailorBusy(false); }
  }

  async function copyCover() {
    if (!tailor) return;
    try {
      await navigator.clipboard.writeText(tailor.cover_letter);
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    } catch { setErr("複製失敗"); }
  }

  async function openApply() {
    if (!job) return;
    setErr(null); setApplyBusy(true);
    try {
      const r = await openApplyPage(job.url);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "開啟失敗"); }
    } catch { setErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  }

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="lg"
      title={job ? `${job.title} · ${job.company}` : ""}>
      {job && (
        <Stack gap="lg">
          {err && <Text c="danger.6" size="sm">{err}</Text>}

          {/* 比對 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>比對</Text>
              {hasUrl && (
                <Button size="compact-sm" variant="light" onClick={runMatch} loading={matchBusy} disabled={!canMatch}>
                  {match ? "重新比對" : "比對"}
                </Button>
              )}
            </Group>
            {!canMatch && <Text c="amber.5" size="xs">請先到「履歷健檢」上傳履歷。</Text>}
            {!hasUrl && <Text c="dimmed" size="xs">此職缺無可用網址，無法比對。</Text>}
            <BusyHint active={matchBusy} label="比對中" />
            {match && (
              <Stack gap={6} mt="sm">
                <Group align="baseline" gap={6}>
                  <Text c="teal.5" fw={700} ff="'Space Grotesk', sans-serif" size="xl">{match.score}</Text>
                  <Text c="dimmed" size="xs">/ 100</Text>
                </Group>
                <Progress value={match.score} color="teal" size="sm" />
                <Text size="xs" fw={600}>契合理由</Text>
                <List size="xs" spacing={2}>{match.reasons.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
                <Text size="xs" fw={600}>缺少技能 / 待補強</Text>
                <List size="xs" spacing={2}>{match.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
              </Stack>
            )}
          </Paper>

          {/* 研究 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between">
              <Text fw={600}>公司研究</Text>
              <ResearchButton company={job.company} />
            </Group>
          </Paper>

          {/* 客製化 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>客製化</Text>
              {hasUrl && (
                <Button size="compact-sm" variant="light" onClick={runTailor} loading={tailorBusy} disabled={!canMatch}>
                  {tailor ? "重新生成" : "客製化"}
                </Button>
              )}
            </Group>
            {!hasUrl && <Text c="dimmed" size="xs">此職缺無可用網址，無法客製化。</Text>}
            <BusyHint active={tailorBusy} label="生成中" />
            {tailor && (
              <Stack gap="md" mt="sm">
                {tailor.resume_tips.length > 0 && (
                  <div>
                    <Group gap={8} mb={4}>
                      <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                      <Text fw={600} size="sm">要強調的重點</Text>
                    </Group>
                    <List size="sm" spacing={4}>{tailor.resume_tips.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
                  </div>
                )}
                {tailor.resume_adjustments.length > 0 && (
                  <div>
                    <Text fw={600} size="sm" mb={4}>建議調整</Text>
                    <List size="sm" spacing={4}>{tailor.resume_adjustments.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
                  </div>
                )}
                {tailor.missing_keywords.length > 0 && (
                  <div>
                    <Text fw={600} size="sm" mb={4}>該補的關鍵字</Text>
                    <Group gap={6}>{tailor.missing_keywords.map((k, i) => <Text key={i} size="sm" c="amber.5">{k}</Text>)}</Group>
                  </div>
                )}
                <div>
                  <Group justify="space-between" mb={4}>
                    <Text fw={600} size="sm">求職信</Text>
                    <ActionIcon variant="subtle" color="gray" onClick={copyCover} title="複製求職信">
                      {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                    </ActionIcon>
                  </Group>
                  <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>{tailor.cover_letter}</Text>
                </div>
                <Button leftSection={<IconExternalLink size={16} />} onClick={openApply} loading={applyBusy} w="fit-content">
                  開啟投遞頁
                </Button>
                <BusyHint active={applyBusy} label="開啟中" />
              </Stack>
            )}
          </Paper>

          <Anchor href={job.url || undefined} target="_blank" size="xs" c="dimmed">
            {job.url ? "去 104 看原始職缺" : ""}
          </Anchor>
        </Stack>
      )}
    </Drawer>
  );
}
```

> 若 `Badge` 未被使用會被 tsc unused 擋——上面未用到 `Badge`，請從 import 移除（保留實際用到的：ActionIcon/Anchor/Button/Drawer/Group/List/Paper/Progress/Stack/Text/ThemeIcon）。

- [ ] **Step 3: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功。若報 unused import（如 `Badge`），移除之。

- [ ] **Step 4: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（未動後端）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/JobCardDrawer.tsx
git commit -m "feat(sentinel): JobCardDrawer 職缺卡片(比對/研究/客製化)+api.ts（SP17）"
```

---

### Task 4: 求職中心列點開卡片

**Files:**
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`（Drawer 狀態、列可點、內按鈕 stopPropagation）
- 驗證：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：`<JobCardDrawer job opened onClose />`＋`CardJob` 型別（Task 3）；`PipelineJob`（既有）。

- [ ] **Step 1: Dashboard 匯入與 Drawer 狀態**

`sentinel/web/frontend/src/Dashboard.tsx`：
- import 補：`import JobCardDrawer, { type CardJob } from "./JobCardDrawer";`
- 在元件內（既有 useState 附近）加：
```typescript
  const [cardJob, setCardJob] = useState<CardJob | null>(null);
  const openCard = (j: PipelineJob) => () =>
    setCardJob({ code: j.code, company: j.company, title: j.title, url: j.job_url || j.url, salary: j.salary });
```
（`PipelineJob` 有 `job_url` 與 `url`；管道職缺優先用 `job_url`，手動追蹤者用 `url`。）

- [ ] **Step 2: 職缺管道各列可點開卡片**

在職缺管道五個群組（面試中/已投遞/已客製化/已比對/有興趣）的每個 `<Row key=…>` 外層，讓「列本體」可點觸發 `openCard(j)`；列內既有的互動元件（gcal/看職缺 Anchor/知道了 ActionIcon/對話串/取消追蹤 ActionIcon/`ResearchButton`）加 `onClick` 包一層 `stopPropagation` 避免誤觸。

具體做法：`Row` 元件本身不改；在每個群組 `.map` 產生的 `<Row>` 外，改成在 `<Row>` 上掛可點區域。因 `Row` 是 `Group`，最小改動是：把每列最外層可點的文字/公司區塊包一個 `onClick={openCard(j)} style={{cursor:"pointer", flex:1, minWidth:0}}` 的 `<div>`；列內的 `ActionIcon`/`Anchor`/`ResearchButton` 各自加 `onClick={(e) => e.stopPropagation()}`（ResearchButton 若不接受 onClick，改用包一層 `<div onClick={e=>e.stopPropagation()}>` 包住它）。

對「面試中」群組（含 gcal/看職缺/對話串/知道了）：把公司·職稱那個 `<Text>` 包成可點 `<div onClick={openCard(j)} style={{cursor:"pointer",minWidth:0,flex:1}}>`；右側 `Group` 內每個 `ActionIcon`/`Anchor` 保持原樣但各加 `onClick={(e)=>e.stopPropagation()}`（`component="a"` 的 Anchor/ActionIcon 也要，避免冒泡到列）。ResearchButton 用 `<span onClick={(e)=>e.stopPropagation()}>` 包住。

對「已投遞/已客製化/已比對/有興趣」群組：把公司·職稱 `<Text>`（含 `Star`/`Badge`）那個 `<Group>` 包成可點；尾端「取消追蹤」`ActionIcon` 加 `onClick` 先 `e.stopPropagation()` 再執行 `untrack(j.code)`（把既有 `onClick={untrack(j.code)}` 改為 `onClick={(e)=>{e.stopPropagation(); untrack(j.code)();}}`）；`ResearchButton` 用 `<span onClick stopPropagation>` 包住。

> 目標：點列的「文字區」開卡片，點列內任何按鈕/連結不開卡片。實作者可自行選最小侵入的包法，但務必確保：(1) 五個群組的列都能開卡片；(2) 既有列內按鈕行為完全不變（gcal 連結、知道了/還原、取消追蹤、看職缺、對話串、研究）。

- [ ] **Step 3: 掛載 Drawer**

在 `Dashboard` return 的 `<PageContainer>` 內最後（或最外層合適處）加：
```tsx
      <JobCardDrawer job={cardJob} opened={cardJob !== null} onClose={() => setCardJob(null)} />
```

- [ ] **Step 4: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功。

- [ ] **Step 5: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠。

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 求職中心列點開職缺卡片 Drawer（SP17）"
```

---

### Task 5: tracked_codes 判定 ＋ 移除 TailorPage/導覽

**Files:**
- Modify: `sentinel/web/frontend/src/FindJobsPage.tsx`（trackedCodes 改用 `tracked_codes`，移除 `TRACKED_STATES`）
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`（同上）
- Modify: `sentinel/web/frontend/src/Sidebar.tsx`（PageKey/NAV 移除 tailor）
- Modify: `sentinel/web/frontend/src/App.tsx`（移除 TailorPage import 與 div）
- Delete: `sentinel/web/frontend/src/TailorPage.tsx`
- 驗證：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：`SnapshotResp.tracked_codes`（Task 3 api.ts）。

- [ ] **Step 1: FindJobsPage 用 tracked_codes**

`sentinel/web/frontend/src/FindJobsPage.tsx`：
- 移除模組層 `const TRACKED_STATES = new Set([...])`。
- 把 `const trackedCodes = new Set((snap.data?.pipeline ?? []).filter(...).map(...)...)` 改為：
```typescript
  const trackedCodes = new Set(snap.data?.tracked_codes ?? []);
```

- [ ] **Step 2: ChatPage 用 tracked_codes**

`sentinel/web/frontend/src/ChatPage.tsx`：同 Step 1——移除 `TRACKED_STATES`，`trackedCodes` 改為 `new Set(snap.data?.tracked_codes ?? [])`。

- [ ] **Step 3: 移除 TailorPage 與導覽項**

- `Sidebar.tsx`：`PageKey` 移除 `"tailor"`；`NAV` 移除 `{ key: "tailor", ... }` 那項；若 `IconWand` 不再用，從 import 移除。
- `App.tsx`：移除 `import TailorPage from "./TailorPage";` 與 `<div style={{ display: page === "tailor" ? … }}><TailorPage /></div>`。
- 刪檔：
```bash
git rm sentinel/web/frontend/src/TailorPage.tsx
```

- [ ] **Step 4: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功。若報殘留 import（TailorPage、IconWand、TRACKED_STATES 相關）清乾淨。

- [ ] **Step 5: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠。

- [ ] **Step 6: Commit**

```bash
git add -A sentinel/web/frontend/src/
git commit -m "feat(sentinel): 已追蹤判定改用 tracked_codes + 移除 TailorPage/導覽（SP17）"
```

---

## Self-Review 註記（計畫作者）

- **Spec coverage：** 兩新欄+遷移+merge(Task1)、API 存 JSON/GET/{code}/tracked_codes(Task2)、JobCardDrawer+api.ts(Task3)、Dashboard 列點開(Task4)、tracked_codes 判定+移除 TailorPage(Task5) 全覆蓋。
- **不改 match/tailor 端點：** Task3 卡片在前端拿到 `POST /api/match`/`/api/tailor` 結果後，另呼叫 `POST /api/tracked`（帶 match_json/tailor_json）快取——端點回傳未改，FindJobsPage 的 inline 比對不受影響（SP16「比對≠追蹤」保留）。
- **SP16 相容：** Task2 把 `track_job` 改用 `merge_tracked_job`；state_hint 對應（tailor_json→tailored、match_json/score→matched、皆無→interested）保證 SP16 `test_web_tracked.py` 全數回歸不破（無 score→interested、有 score→matched、不降級終端、保留 created_at）。
- **循環 import：** `merge_tracked_job` 內 `from . import pipeline` 延遲 import，避免 store↔pipeline 模組層循環。
- **型別一致：** `TrackReq`(api.ts) 加 `match_json`/`tailor_json`；`getTrackedJob`/`TrackedCard`/`CardJob` 跨 Task3/4 一致；`SnapshotResp.tracked_codes` Task3 定義、Task5 使用。
- **遷移安全：** Task1 `_migrate` 用 PRAGMA 檢查後冪等 ALTER，`test_old_db_gains_columns` 用真的缺欄舊 schema 驗證。
- **stopPropagation：** Task4 明確要求列內既有按鈕都擋冒泡，保住 SP7/SP15/16 既有列內行為。
