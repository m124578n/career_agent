# 面試紀錄 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `TrackedJob` 加 `interviews_json`（多筆 `{when, content}`），JobCardDrawer 加「面試紀錄」編輯區（PUT 整列），並讓 agent 用 `interview_note` 確認卡 append 一筆。

**Architecture:** 比照 SP20 offer_json 的持久化樣式：TrackedJob 加 interviews_json（冪等 migration）＋兩個 store helper（set_interviews 整列取代、add_interview_note 附加）。卡片編輯走 `PUT /api/tracked/{code}/interviews`；agent 走既有 apply_update（interview_note field，append）。

**Tech Stack:** Python 3.12 / Pydantic v2 / SQLite / FastAPI；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- **需 code**：面試紀錄以 tracked_jobs（code PK）持久化；無 code 的職缺不可記（卡片提示、apply_update 回 ok=False）。
- **建列 or 更新、保留欄位**：`set_interviews`/`add_interview_note` 對不存在的 code 建 tracked 列、存在則只更新 interviews_json＋updated_at，不動其他欄位（尤其 state/offer_json）。
- **兩條寫入語意**：卡片編輯走 `PUT`（整列取代）；agent 走 `apply_update interview_note`（append 一筆）。互不干擾。
- **相容加法式**：`interviews_json`/`InterviewNote`/`interviews` 皆加法；`_migrate` 冪等 ALTER 不丟資料；既有 tracked CRUD、offer/match/tailor、SSE、卡片行為不變。
- **韌性**：壞 interviews_json 解析 try/except → 視為空列。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 127.0.0.1。
- **測試（後端）**：於 `sentinel/` 用 `./.venv/Scripts/python.exe -m pytest -q`。
- **測試（前端）**：於 `sentinel/web/frontend/` 用 `npm run build`。

---

## File Structure

- `sentinel/src/career_sentinel/models.py` — `InterviewNote` ＋ `TrackedJob.interviews_json`（T1）。
- `sentinel/src/career_sentinel/store.py` — schema/migrate/load/get/upsert 加欄 ＋ `set_interviews`/`add_interview_note`（T1）。
- `sentinel/src/career_sentinel/web/app.py` — GET 回 interviews ＋ `PUT /api/tracked/{code}/interviews`（T2）。
- `sentinel/src/career_sentinel/chat.py` — apply_update `interview_note` ＋ ALLOWED ＋ 合約（T3）。
- `sentinel/web/frontend/src/api.ts` ＋ `JobCardDrawer.tsx` — 面試紀錄型別/端點/編輯區（T4）。
- `sentinel/web/frontend/src/ChatPage.tsx` — interview_note 卡（T5）。
- 測試：`test_tracked_jobs_store.py`（T1）、`test_web_tracked.py`（T2）、`test_chat_apply.py`/`test_chat_tools.py`（T3）。

---

### Task 1: 資料模型 ＋ store（interviews_json ＋ 兩 helper）

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`、`sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_tracked_jobs_store.py`

**Interfaces:**
- Produces:
  - `models.InterviewNote(when: str = "", content: str = "")`。
  - `TrackedJob.interviews_json: str = ""`。
  - `store.set_interviews(conn, code, notes: list[InterviewNote]) -> None`（整列取代、建列或保留欄位）。
  - `store.add_interview_note(conn, code, note: InterviewNote) -> None`（附加）。
  - load/get/upsert 讀寫 interviews_json。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_tracked_jobs_store.py` 末尾加：

```python
def test_set_interviews_creates_and_roundtrips(tmp_path):
    from career_sentinel.models import InterviewNote
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_interviews(conn, "iv1", [InterviewNote(when="2026-07-10 一面", content="系統設計")])
    tj = store.get_tracked_job(conn, "iv1")
    assert tj is not None
    import json
    notes = [InterviewNote.model_validate(x) for x in json.loads(tj.interviews_json)]
    assert len(notes) == 1 and notes[0].when == "2026-07-10 一面" and notes[0].content == "系統設計"


def test_set_interviews_preserves_other_fields(tmp_path):
    from career_sentinel.models import InterviewNote, OfferDetail
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "iv2", "offer", offer=OfferDetail(salary_year=999))
    store.set_interviews(conn, "iv2", [InterviewNote(when="二面", content="主管面")])
    tj = store.get_tracked_job(conn, "iv2")
    assert tj.state == "offer" and tj.offer_json != ""       # 不動 state/offer
    assert "主管面" in tj.interviews_json


def test_add_interview_note_appends(tmp_path):
    from career_sentinel.models import InterviewNote
    conn = store.connect(tmp_path / "db.sqlite")
    store.add_interview_note(conn, "iv3", InterviewNote(when="一面", content="A"))
    store.add_interview_note(conn, "iv3", InterviewNote(when="二面", content="B"))
    import json
    notes = json.loads(store.get_tracked_job(conn, "iv3").interviews_json)
    assert [n["content"] for n in notes] == ["A", "B"]


def test_add_interview_note_bad_json_survives(tmp_path):
    from career_sentinel.models import InterviewNote, TrackedJob
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="iv4", interviews_json="{not json"))
    store.add_interview_note(conn, "iv4", InterviewNote(when="x", content="y"))
    import json
    notes = json.loads(store.get_tracked_job(conn, "iv4").interviews_json)
    assert len(notes) == 1 and notes[0]["content"] == "y"


def test_migrate_adds_interviews_json(tmp_path):
    import sqlite3
    p = tmp_path / "db.sqlite"
    raw = sqlite3.connect(str(p))
    raw.execute(
        "CREATE TABLE tracked_jobs (code TEXT PRIMARY KEY, company TEXT NOT NULL DEFAULT '', "
        "title TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', salary TEXT NOT NULL DEFAULT '', "
        "state TEXT NOT NULL DEFAULT 'interested', match_score INTEGER, created_at TEXT NOT NULL DEFAULT '', "
        "updated_at TEXT NOT NULL DEFAULT '', match_json TEXT NOT NULL DEFAULT '', "
        "tailor_json TEXT NOT NULL DEFAULT '', offer_json TEXT NOT NULL DEFAULT '')"
    )
    raw.execute("INSERT INTO tracked_jobs (code, state) VALUES ('old1', 'matched')")
    raw.commit(); raw.close()
    conn = store.connect(p)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tracked_jobs)")}
    assert "interviews_json" in cols
    got = store.get_tracked_job(conn, "old1")
    assert got is not None and got.state == "matched" and got.interviews_json == ""
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: FAIL（`InterviewNote`/`set_interviews`/`interviews_json` 不存在）

- [ ] **Step 3: models 加 InterviewNote ＋ TrackedJob 欄（`models.py`）**

在 `class TrackedJob` 之前加：

```python
class InterviewNote(BaseModel):
    when: str = ""      # 面試時間（自由字串，如 "2026-07-10 14:00 一面"）
    content: str = ""   # 面試內容/心得
```

`class TrackedJob` 的 `offer_json: str = ""` 後加：

```python
    interviews_json: str = ""
```

- [ ] **Step 4: store schema/migrate/欄位（`store.py`）**

`_SCHEMA` 的 `offer_json` 行改為含逗號並加 interviews_json 行：

```python
    tailor_json TEXT NOT NULL DEFAULT '',
    offer_json TEXT NOT NULL DEFAULT '',
    interviews_json TEXT NOT NULL DEFAULT ''
);
```

`_migrate` 欄位迴圈加 `interviews_json`：

```python
    for col in ("match_json", "tailor_json", "offer_json", "interviews_json"):
```

`load_tracked_jobs` 改為（SELECT 末加 interviews_json、解構加 iv、TrackedJob 加 interviews_json）：

```python
def load_tracked_jobs(conn: sqlite3.Connection) -> list[TrackedJob]:
    rows = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json, interviews_json FROM tracked_jobs ORDER BY updated_at DESC"
    )
    return [
        TrackedJob(
            code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
            match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
            tailor_json=tj or "", offer_json=oj or "", interviews_json=iv or "",
        )
        for c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj, iv in rows
    ]
```

`get_tracked_job` 同改：

```python
def get_tracked_job(conn: sqlite3.Connection, code: str) -> TrackedJob | None:
    row = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json, interviews_json FROM tracked_jobs WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        return None
    c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj, iv = row
    return TrackedJob(
        code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
        match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
        tailor_json=tj or "", offer_json=oj or "", interviews_json=iv or "",
    )
```

`upsert_tracked_job` 改為 13 欄：

```python
def upsert_tracked_job(conn: sqlite3.Connection, job: TrackedJob) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_jobs "
        "(code, company, title, url, salary, state, match_score, created_at, updated_at, match_json, tailor_json, offer_json, interviews_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (job.code, job.company, job.title, job.url, job.salary, job.state,
         job.match_score, job.created_at, job.updated_at, job.match_json, job.tailor_json,
         job.offer_json, job.interviews_json),
    )
    conn.commit()
```

- [ ] **Step 5: store models import 加 InterviewNote ＋ 兩 helper（`store.py`）**

頂部 models import 清單加 `InterviewNote`（與 OfferDetail 同區）。在 `set_tracked_state` 之後加：

```python
def set_interviews(conn: sqlite3.Connection, code: str, notes: list[InterviewNote]) -> None:
    """整列取代某職缺的面試紀錄；不存在則建列；保留其他欄位。"""
    now = datetime.now().isoformat(timespec="seconds")
    interviews_json = json.dumps([n.model_dump() for n in notes], ensure_ascii=False)
    existing = get_tracked_job(conn, code)
    if existing is not None:
        existing.interviews_json = interviews_json
        existing.updated_at = now
        upsert_tracked_job(conn, existing)
    else:
        upsert_tracked_job(conn, TrackedJob(
            code=code, created_at=now, updated_at=now, interviews_json=interviews_json))


def add_interview_note(conn: sqlite3.Connection, code: str, note: InterviewNote) -> None:
    """附加一筆面試紀錄（agent 用）。壞 JSON 視為空列。"""
    existing = get_tracked_job(conn, code)
    notes: list[InterviewNote] = []
    if existing is not None and existing.interviews_json:
        try:
            notes = [InterviewNote.model_validate(x) for x in json.loads(existing.interviews_json)]
        except Exception:
            notes = []
    notes.append(note)
    set_interviews(conn, code, notes)
```

- [ ] **Step 6: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: PASS

- [ ] **Step 7: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_tracked_jobs_store.py
git commit -m "feat(sentinel): InterviewNote + tracked_jobs.interviews_json + set_interviews/add_interview_note（面試紀錄）"
```

---

### Task 2: 端點（GET 回 interviews ＋ PUT 整列）

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_tracked.py`

**Interfaces:**
- Consumes: Task 1 `store.set_interviews`、`get_tracked_job` 的 interviews_json、`models.InterviewNote`。
- Produces: `GET /api/tracked/{code}` 回傳含 `interviews`；`PUT /api/tracked/{code}/interviews`（body `{notes: [InterviewNote]}`）。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_web_tracked.py` 末尾加：

```python
def test_get_tracked_includes_interviews(tmp_path):
    from career_sentinel.models import InterviewNote
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_interviews(conn, "iv1", [InterviewNote(when="一面", content="做題")])
    got = _client(tmp_path).get("/api/tracked/iv1").json()
    assert got["interviews"] == [{"when": "一面", "content": "做題"}]


def test_get_tracked_missing_interviews_empty(tmp_path):
    got = _client(tmp_path).get("/api/tracked/none").json()
    assert got["interviews"] == []


def test_put_interviews_replaces(tmp_path):
    c = _client(tmp_path)
    r = c.put("/api/tracked/iv2/interviews", json={"notes": [
        {"when": "一面", "content": "A"}, {"when": "二面", "content": "B"}]})
    assert r.status_code == 200 and r.json()["count"] == 2
    got = c.get("/api/tracked/iv2").json()
    assert [n["content"] for n in got["interviews"]] == ["A", "B"]
    # 再 PUT 整列取代
    c.put("/api/tracked/iv2/interviews", json={"notes": [{"when": "終面", "content": "C"}]})
    got2 = c.get("/api/tracked/iv2").json()
    assert [n["content"] for n in got2["interviews"]] == ["C"]
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_tracked.py -q`
Expected: FAIL（GET 無 interviews key → KeyError；PUT 404）

- [ ] **Step 3: import InterviewNote（`app.py`）**

app.py 頂部 `from ..models import ...` 那行加入 `InterviewNote`：

```python
from ..models import ChatMessage, ChatState, InterviewNote, JobPreferences, OfferDetail, Settings, SuggestedUpdate, interview_key
```

（注意：SP22 之後此行已無 ResumeState/TrackedJob；只加 `InterviewNote`，保持其餘不變。）

- [ ] **Step 4: `GET /api/tracked/{code}` 加 interviews（`app.py`）**

`tracked_get` 兩個 return 各加 `interviews`：

```python
    @app.get("/api/tracked/{code}")
    def tracked_get(code: str) -> dict:
        tj = store.get_tracked_job(_conn(), code)
        if tj is None:
            return {"code": code, "found": False, "state": "", "match_score": None,
                    "match": None, "tailor": None, "offer": None, "interviews": []}
        return {
            "code": tj.code, "found": True, "state": tj.state, "match_score": tj.match_score,
            "match": json.loads(tj.match_json) if tj.match_json else None,
            "tailor": json.loads(tj.tailor_json) if tj.tailor_json else None,
            "offer": json.loads(tj.offer_json) if tj.offer_json else None,
            "interviews": json.loads(tj.interviews_json) if tj.interviews_json else [],
        }
```

- [ ] **Step 5: 加 `PUT /api/tracked/{code}/interviews`（`app.py`）**

在 tracked 相關端點附近加：

```python
    class _InterviewsReq(BaseModel):
        notes: list[InterviewNote]

    @app.put("/api/tracked/{code}/interviews")
    def set_interviews_ep(code: str, req: _InterviewsReq) -> dict:
        if not code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        store.set_interviews(_conn(), code, req.notes)
        return {"status": "ok", "count": len(req.notes)}
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
git commit -m "feat(sentinel): GET /api/tracked 回 interviews + PUT /api/tracked/{code}/interviews（面試紀錄）"
```

---

### Task 3: apply_update `interview_note` ＋ 合約（agent append）

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_apply.py`、`sentinel/tests/test_chat_tools.py`

**Interfaces:**
- Consumes: Task 1 `store.add_interview_note`、`models.InterviewNote`。
- Produces: `apply_update` 支援 field `interview_note`（op `set`，payload `{code, when, content}`，append）；`ALLOWED` 含 interview_note；合約含 interview_note 提議。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_chat_apply.py` 末尾加：

```python
def test_apply_interview_note_appends(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="interview_note", op="set", payload={
        "code": "abc12", "when": "2026-07-10 一面", "content": "問系統設計"}))
    assert r.ok
    import json
    notes = json.loads(store.get_tracked_job(conn, "abc12").interviews_json)
    assert len(notes) == 1 and notes[0]["when"] == "2026-07-10 一面" and notes[0]["content"] == "問系統設計"


def test_apply_interview_note_missing_code(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="interview_note", op="set", payload={"content": "x"}))
    assert not r.ok and "代碼" in r.message
```

在 `sentinel/tests/test_chat_tools.py` 末尾加：

```python
def test_system_prompt_mentions_interview_note():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "interview_note" in p
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py tests/test_chat_tools.py -q`
Expected: FAIL（interview_note 未允許；prompt 無 interview_note）

- [ ] **Step 3: `ALLOWED` 加 interview_note（`chat.py`）**

`ALLOWED` dict 加：

```python
    "interview_note": {"set"},
```

- [ ] **Step 4: apply_update 加 interview_note 分支（`chat.py`）**

在管道動作分支（`if upd.field in ("track", ...)`）之後、memory 分支之前加：

```python
    if upd.field == "interview_note":
        payload = upd.payload or {}
        code = str(payload.get("code", "")).strip()
        if not code:
            return ApplyResult(ok=False, message="缺少職缺代碼")
        from .models import InterviewNote
        store.add_interview_note(conn, code, InterviewNote(
            when=str(payload.get("when", "")), content=str(payload.get("content", ""))))
        return ApplyResult(ok=True)
```

- [ ] **Step 5: `_CONTRACT` 加 interview_note 範例與規則（`chat.py`）**

把 negotiate 範例那行（結尾無逗號、後接 `]}</suggestions>`）補逗號並加 interview_note 範例行：

```python
  {"field": "negotiate", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}},
  {"field": "interview_note", "op": "set", "payload": {"code": "abc12", "when": "2026-07-10 14:00 一面", "content": "問了系統設計與過往專案"}}
]}</suggestions>
```

在 negotiate 規則之後、`- 沒有要更新時...` 之前插入：

```python
- 面試紀錄（interview_note/set）：使用者描述某職缺的面試（時間、問了什麼、心得）時，提議
  {"field": "interview_note", "op": "set", "payload": {"code": "...", "when": "...", "content": "..."}}。
  payload.code 必來自 get_pipeline/search_jobs 的實際結果、不得杜撰；只提議，按下確認才記。
```

- [ ] **Step 6: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py tests/test_chat_tools.py -q`
Expected: PASS

- [ ] **Step 7: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_apply.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): apply_update interview_note（agent append）+ 合約（面試紀錄）"
```

---

### Task 4: 前端 api.ts ＋ JobCardDrawer 面試紀錄區

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`、`sentinel/web/frontend/src/JobCardDrawer.tsx`

**Interfaces:**
- Consumes: Task 2 `GET /api/tracked/{code}`（interviews）、`PUT /api/tracked/{code}/interviews`。
- Produces: `InterviewNote` 型別、`setInterviews`；Drawer 面試紀錄編輯區。

- [ ] **Step 1: api.ts 加型別與函式**

在 `TrackedCard` 型別附近加：

```ts
export interface InterviewNote {
  when: string;
  content: string;
}
```

`TrackedCard` interface 加 `interviews: InterviewNote[];`（若 TrackedCard 型別存在；否則加在 getTrackedJob 回傳處理）。並加函式：

```ts
export async function setInterviews(code: string, notes: InterviewNote[]): Promise<Response> {
  return fetch(`/api/tracked/${encodeURIComponent(code)}/interviews`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes }),
  });
}
```

- [ ] **Step 2: JobCardDrawer 匯入與 state（`JobCardDrawer.tsx`）**

`./api` import 加 `setInterviews, type InterviewNote`；`@mantine/core` 確認有 `Textarea`/`TextInput`/`ActionIcon`（既有）。加 state：

```tsx
  const [notes, setNotes] = useState<InterviewNote[]>([]);
  const [ivWhen, setIvWhen] = useState("");
  const [ivContent, setIvContent] = useState("");
  const [ivBusy, setIvBusy] = useState(false);
```

在既有「開啟時載入快取」的 `getTrackedJob(...).then(c => {...})` 裡補：`setNotes(Array.isArray(c.interviews) ? c.interviews : []);`（開啟時重置也要 `setNotes([])`）。

- [ ] **Step 3: 面試紀錄操作函式（`JobCardDrawer.tsx`）**

```tsx
  const saveNotes = async (next: InterviewNote[]) => {
    if (!job) return;
    setIvBusy(true); setErr(null);
    try {
      const r = await setInterviews(job.code, next);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "儲存失敗"); return; }
      setNotes(next);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setIvBusy(false); }
  };
  const addNote = async () => {
    if (!ivWhen.trim() && !ivContent.trim()) return;
    await saveNotes([...notes, { when: ivWhen.trim(), content: ivContent.trim() }]);
    setIvWhen(""); setIvContent("");
  };
  const removeNote = async (i: number) => {
    await saveNotes(notes.filter((_, idx) => idx !== i));
  };
```

- [ ] **Step 4: 面試紀錄 UI 區（`JobCardDrawer.tsx`）**

在 Drawer 的 `<Stack gap="lg">` 內（狀態區附近）插入：

```tsx
          {/* 面試紀錄 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} mb="sm">面試紀錄</Text>
            {!job.code && <Text c="amber.5" size="xs">此職缺無代碼，無法記錄面試。</Text>}
            {job.code && (
              <Stack gap="sm">
                {[...notes].sort((a, b) => (a.when || "").localeCompare(b.when || "")).map((n, i) => (
                  <Group key={i} justify="space-between" wrap="nowrap" align="flex-start"
                    bg="dark.7" px="sm" py={6} style={{ borderRadius: 6 }}>
                    <div style={{ minWidth: 0 }}>
                      <Text size="xs" c="teal.5" ff="monospace">{n.when || "（未填時間）"}</Text>
                      <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{n.content}</Text>
                    </div>
                    <ActionIcon variant="subtle" color="gray" size="sm" title="刪除這筆"
                      onClick={() => removeNote(notes.indexOf(n))} disabled={ivBusy}>
                      <IconX size={14} />
                    </ActionIcon>
                  </Group>
                ))}
                {notes.length === 0 && <Text size="xs" c="dimmed">尚無面試紀錄。</Text>}
                <TextInput label="時間" placeholder="2026-07-10 14:00 一面" value={ivWhen}
                  onChange={(e) => setIvWhen(e.currentTarget.value)} />
                <Textarea label="內容" autosize minRows={2} value={ivContent}
                  onChange={(e) => setIvContent(e.currentTarget.value)} />
                <Button size="compact-sm" onClick={addNote} loading={ivBusy} w="fit-content">新增紀錄</Button>
              </Stack>
            )}
          </Paper>
```

（`IconX` 需在 `@tabler/icons-react` import；`Paper`/`Stack`/`Group`/`Text`/`TextInput`/`Textarea`/`Button`/`ActionIcon` 多為既有 import——缺的補上。）

- [ ] **Step 5: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（無型別/未用 import 錯誤）

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/JobCardDrawer.tsx
git commit -m "feat(sentinel): JobCardDrawer 面試紀錄編輯區 + setInterviews api（面試紀錄）"
```

---

### Task 5: 聊天 interview_note 卡

**Files:**
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`

**Interfaces:**
- Consumes: Task 3 的 interview_note（走 apply_update）；既有 SuggestionCard/PIPE_FIELDS/FIELD_LABEL。

- [ ] **Step 1: FIELD_LABEL ＋ PIPE_FIELDS 加 interview_note（`ChatPage.tsx`）**

`FIELD_LABEL` 加 `interview_note: "面試紀錄"`。

找到 SuggestionCard 內的 `const PIPE_FIELDS = [...]`，加入 `"interview_note"`：

```tsx
  const PIPE_FIELDS = ["track", "job_offer", "job_reject", "job_reset", "untrack", "interview_note"];
```

- [ ] **Step 2: interview_note 的卡片 label（`ChatPage.tsx`）**

在 SuggestionCard 的 `pipeLabel` 計算加 interview_note 分支（顯示時間＋內容）：

```tsx
  const pipeLabel =
    s.field === "track" ? `${p.company ?? ""} · ${p.title ?? ""}`
    : s.field === "job_offer"
      ? `${p.company ?? p.code ?? ""}${p.salary_year ? ` · 年薪 ${p.salary_year}` : p.salary_month ? ` · 月薪 ${p.salary_month}` : ""}`
    : s.field === "interview_note"
      ? `${p.when ?? ""}${p.content ? `：${p.content}` : ""}`
    : `${p.company ?? p.code ?? ""}`;
```

（其餘 SuggestionCard 邏輯不變；interview_note 屬 PIPE_FIELDS，走 apply_update、成功後 invalidate snapshot。）

- [ ] **Step 3: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（無型別/未用 import 錯誤）

- [ ] **Step 4: Commit**

```bash
git add sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天 interview_note 提議卡（面試紀錄）"
```

---

## Self-Review

**Spec coverage：**
- InterviewNote + TrackedJob.interviews_json + migration + set_interviews/add_interview_note → T1 ✅
- GET 回 interviews + PUT 整列 → T2 ✅
- apply_update interview_note（append）+ ALLOWED + 合約 → T3 ✅
- JobCardDrawer 面試紀錄編輯區（列出/新增/刪除/PUT/需 code 提示）→ T4 ✅
- 聊天 interview_note 卡（FIELD_LABEL/PIPE_FIELDS/label）→ T5 ✅
- Global Constraints（需 code、建列保留欄位、兩條寫入語意、相容加法、韌性）各 Task 遵守 ✅

**Placeholder scan：** 無 TBD/TODO；每步含完整程式碼與確切指令。

**Type consistency：** `InterviewNote{when,content}` 於 models/api.ts/Drawer/合約一致；`set_interviews(conn,code,notes)`/`add_interview_note(conn,code,note)` 於 store/app/apply_update/測試一致；`interviews_json` 於 model/store 13 欄一致；`interviews` 於 GET 回傳、Drawer、TrackedCard 一致；`interview_note` field 於 ALLOWED/apply_update/合約/前端 FIELD_LABEL/PIPE_FIELDS 一致；`setInterviews(code,notes)` PUT body `{notes}` 與端點 `_InterviewsReq{notes}` 一致。
