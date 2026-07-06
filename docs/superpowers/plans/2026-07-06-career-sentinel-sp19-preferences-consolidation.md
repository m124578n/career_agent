# SP19：偏好集中 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `target_title`／`expected_salary` 從 `ResumeState` 搬進單一 `JobPreferences`（與 locations/conditions/avoid 同一偏好），提供 GET/PUT /api/preferences 與我的履歷頁的偏好編輯區。

**Architecture:** 分三步保套件常綠：(1) 先在 `JobPreferences` 加兩欄＋raw-JSON 冪等遷移＋GET/PUT /api/preferences（不動任何讀取點）；(2) 原子化把 diagnose/match/tailor/chat 的讀寫切到 prefs、`GET /api/resume` 拿掉兩欄、移除 `ResumeState` 兩欄，並一次更新所有破掉的測試；(3) 前端偏好區＋api.ts。`keywords`／`is_watched` 全程不動。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、SQLite、pytest；React 18 ＋ Vite ＋ Mantine 7 ＋ TanStack Query。

## Global Constraints

- **is_watched / keywords 完全不動**：`watch.is_watched`、`Settings.watched_keywords`、`SettingsModal`、snapshot 的 is_watched 呼叫全部保持原狀。
- **遷移不丟資料、冪等**：`_migrate_preferences` 在 raw-JSON 層把舊 `ResumeState.target_title/expected_salary` 搬進 prefs（prefs 已有 target_title 就不覆寫），跑幾次安全。
- **單一來源**：搬移後 `target_title`/`expected_salary` 只存在於 `JobPreferences`；比對/客製化/健檢/聊天全讀 prefs；`ResumeState` 不再有這兩欄。
- **相容**：`ResumeState` 移欄靠 Pydantic 忽略多餘 key（不炸舊 JSON）；`/api/match`/`/api/tailor`/`/api/resume/upload`/`/api/resume/import104` 回傳不變；聊天 `apply_update` 的 field 名（target_title/expected_salary）不變、只換儲存目標。
- 後端綁 `127.0.0.1`；前端 `npm run build` 必過。
- 測試：後端 `cd sentinel && ./.venv/Scripts/python.exe -m pytest`；前端 `cd sentinel/web/frontend && npm run build`。

---

### Task 1: JobPreferences 加兩欄 ＋ 遷移 ＋ GET/PUT /api/preferences

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（`JobPreferences` 加 `target_title`/`expected_salary`）
- Modify: `sentinel/src/career_sentinel/store.py`（`connect()` 加 `_migrate_preferences`）
- Modify: `sentinel/src/career_sentinel/web/app.py`（新 GET/PUT /api/preferences；import `JobPreferences`）
- Test: `sentinel/tests/test_preferences.py`（新檔）

**Interfaces:**
- Consumes（既有）：`store.load_preferences`/`save_preferences`。
- Produces：`JobPreferences` 新增 `target_title: str=""`、`expected_salary: int|None=None`；`GET /api/preferences`→`JobPreferences` dict；`PUT /api/preferences`（body `JobPreferences`）。

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_preferences.py`：

```python
import json
import sqlite3
from fastapi.testclient import TestClient
from career_sentinel import store
from career_sentinel.models import JobPreferences, ResumeState
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_preferences_new_fields_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_preferences(conn, JobPreferences(
        target_title="後端工程師", expected_salary=900000,
        locations=["台北"], conditions=["可遠端"], avoid=["博弈"]))
    p = store.load_preferences(conn)
    assert p.target_title == "後端工程師" and p.expected_salary == 900000
    assert p.locations == ["台北"] and p.avoid == ["博弈"]


def test_migrate_copies_from_resume(tmp_path):
    # 舊資料：resume 有 target_title/expected_salary、prefs 尚未有
    p = tmp_path / "db.sqlite"
    store.connect(p).close()  # 建表
    c = sqlite3.connect(str(p))
    c.execute("INSERT OR REPLACE INTO resume (id, data) VALUES (1, ?)",
              (json.dumps({"resume_text": "履歷", "target_title": "後端", "expected_salary": 60000}),))
    c.commit(); c.close()
    conn = store.connect(p)  # connect 應觸發遷移
    pref = store.load_preferences(conn)
    assert pref.target_title == "後端" and pref.expected_salary == 60000


def test_migrate_idempotent_no_overwrite(tmp_path):
    p = tmp_path / "db.sqlite"
    conn = store.connect(p)
    store.save_preferences(conn, JobPreferences(target_title="既有職稱"))
    conn.close()
    c = sqlite3.connect(str(p))
    c.execute("INSERT OR REPLACE INTO resume (id, data) VALUES (1, ?)",
              (json.dumps({"resume_text": "x", "target_title": "舊職稱"}),))
    c.commit(); c.close()
    conn = store.connect(p)  # 再次 connect
    assert store.load_preferences(conn).target_title == "既有職稱"  # 不被覆寫


def test_migrate_no_resume_noop(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_preferences(conn).target_title == ""


def test_get_put_preferences(tmp_path):
    c = _client(tmp_path)
    body = {"target_title": "資料工程師", "expected_salary": 80000,
            "locations": ["新竹"], "conditions": ["彈性工時"], "avoid": ["外派"]}
    r = c.put("/api/preferences", json=body)
    assert r.status_code == 200
    got = c.get("/api/preferences").json()
    assert got["target_title"] == "資料工程師" and got["expected_salary"] == 80000
    assert got["locations"] == ["新竹"] and got["avoid"] == ["外派"]


def test_get_preferences_default(tmp_path):
    got = _client(tmp_path).get("/api/preferences").json()
    assert got["target_title"] == "" and got["expected_salary"] is None and got["locations"] == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_preferences.py -v`
Expected: FAIL（`target_title` 非 JobPreferences 欄位、`/api/preferences` 404）

- [ ] **Step 3: JobPreferences 加兩欄**

`sentinel/src/career_sentinel/models.py` 的 `JobPreferences`（約 177 行）改為：
```python
class JobPreferences(BaseModel):
    target_title: str = ""
    expected_salary: int | None = None
    locations: list[str] = Field(default_factory=list)   # 想要的工作地點
    conditions: list[str] = Field(default_factory=list)  # 軟條件
    avoid: list[str] = Field(default_factory=list)       # 避雷條件
```

- [ ] **Step 4: store 遷移**

`sentinel/src/career_sentinel/store.py`：`connect()` 在 `conn.executescript(_SCHEMA)` 之後（若已有 `_migrate(conn)` 則在其後）加 `_migrate_preferences(conn)`；新增函式（`json` 已 import）：
```python
def _migrate_preferences(conn: sqlite3.Connection) -> None:
    """把舊 ResumeState 的 target_title/expected_salary 搬進 JobPreferences（冪等、raw-JSON 層）。"""
    res_row = conn.execute("SELECT data FROM resume WHERE id = 1").fetchone()
    if res_row is None:
        return
    resume = json.loads(res_row[0])
    old_title = resume.get("target_title") or ""
    old_salary = resume.get("expected_salary")
    if not old_title and old_salary is None:
        return
    pref_row = conn.execute("SELECT data FROM preferences WHERE id = 1").fetchone()
    prefs = json.loads(pref_row[0]) if pref_row else {}
    changed = False
    if not prefs.get("target_title") and old_title:
        prefs["target_title"] = old_title
        changed = True
    if prefs.get("expected_salary") is None and old_salary is not None:
        prefs["expected_salary"] = old_salary
        changed = True
    if changed:
        conn.execute("INSERT OR REPLACE INTO preferences (id, data) VALUES (1, ?)",
                     (json.dumps(prefs, ensure_ascii=False),))
        conn.commit()
```

- [ ] **Step 5: GET/PUT /api/preferences**

`sentinel/src/career_sentinel/web/app.py`：把 `JobPreferences` 加入 `from ..models import (...)` 清單；在設定/偏好相關端點附近新增：
```python
    @app.get("/api/preferences")
    def get_preferences() -> dict:
        return store.load_preferences(_conn()).model_dump()

    @app.put("/api/preferences")
    def put_preferences(prefs: JobPreferences) -> dict:
        store.save_preferences(_conn(), prefs)
        return prefs.model_dump()
```

- [ ] **Step 6: 跑測試確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_preferences.py -v`
Expected: PASS（6 passed）

- [ ] **Step 7: 全測試回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（未動任何讀取點與 ResumeState，既有測試不受影響）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/src/career_sentinel/web/app.py sentinel/tests/test_preferences.py
git commit -m "feat(sentinel): JobPreferences 加 target_title/expected_salary + 遷移 + GET/PUT /api/preferences（SP19）"
```

---

### Task 2: 讀取點切到 prefs ＋ 移除 ResumeState 兩欄 ＋ 更新測試

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（`ResumeState` 移除 `target_title`/`expected_salary`）
- Modify: `sentinel/src/career_sentinel/web/app.py`（diagnose 讀 prefs、GET /api/resume 拿掉兩欄、match/tailor 讀 prefs、移除 `_DiagnoseReq`）
- Modify: `sentinel/src/career_sentinel/chat.py`（build_system_prompt/render/apply_update 改讀寫 prefs）
- Modify（測試更新）：`sentinel/tests/test_web_resume.py`、`test_chat_apply.py`、`test_chat.py`、`test_web_match.py`、`test_resume_store.py`、`test_web_app.py`、`test_web_chat.py`

**Interfaces:**
- Consumes：`store.load_preferences`/`save_preferences`（Task 1 已含 target_title/expected_salary）。
- Produces：`ResumeState` 不再有 `target_title`/`expected_salary`；`POST /api/resume/diagnose` 不收 body；`GET /api/resume` 不回這兩欄。

> 本任務是欄位搬移重構——原子化落地，**以「全套件回歸綠」為完成閘**。先改源碼與測試，最後 `pytest -q` 全綠。

- [ ] **Step 1: ResumeState 移除兩欄**

`sentinel/src/career_sentinel/models.py` 的 `ResumeState` 改為：
```python
class ResumeState(BaseModel):
    resume_text: str = ""
    diagnosis: ResumeDiagnosis | None = None
    source: str = ""
```

- [ ] **Step 2: app.py 讀取點切到 prefs**

`sentinel/src/career_sentinel/web/app.py`：
(a) 移除 `_DiagnoseReq` 類別（約 21-23 行）。
(b) `resume_diagnose` 端點改為（無 body、讀 prefs）：
```python
    @app.post("/api/resume/diagnose")
    def resume_diagnose() -> dict:
        conn = _conn()
        state = store.load_resume(conn)
        if not state.resume_text.strip():
            raise HTTPException(status_code=400, detail="請先上傳履歷")
        prefs = store.load_preferences(conn)
        if not prefs.target_title.strip():
            raise HTTPException(status_code=400, detail="請先在偏好設定目標職稱")
        try:
            result = diagnosis.diagnose(state.resume_text, prefs.target_title, prefs.expected_salary)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="健檢失敗，請重試")
        state.diagnosis = result
        store.save_resume(conn, state)
        return result.model_dump()
```
(c) `resume_get`（GET /api/resume）：移除回傳 dict 裡的 `"target_title"` 與 `"expected_salary"` 兩行（保留 `has_resume`/`chars`/`diagnosis`/`source`）。
(d) `match_job`（/api/match）：把 `state.target_title or "（未指定）"` 改為 `store.load_preferences(conn).target_title or "（未指定）"`。
(e) `tailor_job`（/api/tailor）：同 (d)。

- [ ] **Step 3: chat.py 改讀寫 prefs**

`sentinel/src/career_sentinel/chat.py`：
(a) `build_system_prompt`（約 56-57 行）：`resume.target_title`/`resume.expected_salary` → `prefs.target_title`/`prefs.expected_salary`。
(b) `render`（約 292-293 行）：同 (a)。
(c) `apply_update`（約 171-179 行）：`target_title`/`expected_salary` 的寫入從 `ResumeState` 改為 `JobPreferences`。原本大致是 `state = store.load_resume(conn); state.target_title = ...; store.save_resume(...)`，改為與既有 `locations/conditions/avoid` 相同的 prefs 路徑：
```python
    if upd.field == "target_title":
        prefs = store.load_preferences(conn)
        prefs.target_title = str(upd.value or "")
        store.save_preferences(conn, prefs)
        return _Result(ok=True, message="已更新目標職稱")
    if upd.field == "expected_salary":
        prefs = store.load_preferences(conn)
        try:
            prefs.expected_salary = int(upd.value) if upd.value not in (None, "") else None
        except (TypeError, ValueError):
            return _Result(ok=False, message="期望月薪需為整數")
        store.save_preferences(conn, prefs)
        return _Result(ok=True, message="已更新期望月薪")
```
（`_Result` 與回傳訊息沿用該檔既有型別/字串慣例——請對照 apply_update 現有其他分支的實際回傳寫法照做；上面為結構示意，實作時用檔案裡真正的 Result 類別與訊息。ALLOWED 白名單 field 名不變。）

- [ ] **Step 4: 更新破掉的測試**

逐檔更新（改完後跑全套件驗證）：

`sentinel/tests/test_web_resume.py`：
- `test_resume_diagnose_no_resume_400`：改為 `r = _client(tmp_path).post("/api/resume/diagnose")`（不帶 json），仍 assert 400。
- `test_resume_diagnose_success`：改為——上傳履歷後先設定偏好目標職稱，再無 body 呼叫 diagnose，改用 /api/preferences 驗證目標：
```python
def test_resume_diagnose_success(tmp_path, monkeypatch):
    from career_sentinel import diagnosis
    monkeypatch.setattr(diagnosis, "diagnose", lambda text, title, sal, **kw: ResumeDiagnosis(strengths=["A"], gaps=["B"]))
    c = _client(tmp_path)
    c.post("/api/resume/upload", files={"file": ("r.txt", "履歷".encode("utf-8"), "text/plain")})
    c.put("/api/preferences", json={"target_title": "後端工程師", "expected_salary": 60000,
                                    "locations": [], "conditions": [], "avoid": []})
    r = c.post("/api/resume/diagnose")
    assert r.status_code == 200
    assert r.json()["strengths"] == ["A"]
    assert c.get("/api/resume").json()["diagnosis"]["gaps"] == ["B"]
    assert c.get("/api/preferences").json()["target_title"] == "後端工程師"
```
（`test_resume_diagnose_success` 需 import `ResumeDiagnosis`——該檔頂部已 `from career_sentinel.models import ResumeDiagnosis`。）

`sentinel/tests/test_chat_apply.py`：`test_apply_set_scalar_and_lists`（15-16 行）把
`assert store.load_resume(conn).target_title == "後端工程師"` / `.expected_salary == 900000`
改為
`assert store.load_preferences(conn).target_title == "後端工程師"` / `store.load_preferences(conn).expected_salary == 900000`。

`sentinel/tests/test_chat.py`：`test_system_prompt_embeds_state`（8-13 行）把 target_title/expected_salary 從 `ResumeState(...)` 移到 `JobPreferences(...)`：
```python
    p = chat.build_system_prompt(
        ResumeState(resume_text="Python 五年"),
        Settings(watched_companies=["台積電"], watched_keywords=["Python"]),
        JobPreferences(target_title="後端工程師", expected_salary=900000,
                       locations=["台北"], conditions=["可遠端"], avoid=["博弈"]),
        MemoryState(facts=[MemoryFact(text="通勤以雙北為主")]),
    )
```
（needle 斷言 "後端工程師"/"900000" 不變，現由 prefs 提供。）

`sentinel/tests/test_web_match.py`：`test_match_success`（27 行）`ResumeState(resume_text="我會 Python", target_title="後端工程師")` → 移除 `target_title` kwarg（match 已 mock，target 不影響結果）：`ResumeState(resume_text="我會 Python")`。

`sentinel/tests/test_resume_store.py`：建構 `ResumeState(...)`（約 13 行）移除 `target_title`/`expected_salary` 兩個 kwarg；刪除對應的兩個 assert（`s.target_title`/`s.expected_salary`，約 18-19 行）；保留 resume_text/diagnosis/source 的 round-trip 斷言。

`sentinel/tests/test_web_app.py`（約 176 行）與 `sentinel/tests/test_web_chat.py`（約 179 行）：把建構 `ResumeState(..., target_title=..., expected_salary=...)` 的 kwarg 移除；若該測試的斷言依賴這些值出現在 system prompt/回應中，改用 `store.save_preferences(conn, JobPreferences(target_title=..., expected_salary=...))` 設定（依實際測試意圖）。`test_web_chat.py` 若有斷言 apply target_title 後的儲存位置，改查 `load_preferences`。

> 提醒：Pydantic v2 對 `ResumeState(target_title=...)` 這種「建構時給未定義欄位」會 raise，所以上述所有含這兩個 kwarg 的建構點**都必須移除**該 kwarg，否則測試會在建構時就錯。改完務必跑全套件確認無漏網。

- [ ] **Step 5: 全套件回歸（完成閘）**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠。若有紅：多半是還有某處建構 `ResumeState(target_title=...)` 未清、或某斷言仍查 `load_resume().target_title`——依 Step 4 規則修正。

- [ ] **Step 6: Commit**

```bash
git add -A sentinel/src/career_sentinel/ sentinel/tests/
git commit -m "feat(sentinel): target_title/expected_salary 讀寫改用 JobPreferences（單一來源）（SP19）"
```

---

### Task 3: 前端偏好區 ＋ api.ts

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（`ResumeState` 移除兩欄；新 `JobPreferences` 型別＋`getPreferences`/`putPreferences`；`diagnoseResume` 改無參數）
- Modify: `sentinel/web/frontend/src/ProfilePage.tsx`（新增偏好區，目標/薪資移入，加地點/軟條件/避雷）
- 驗證：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：`GET/PUT /api/preferences`（Task 1）、`POST /api/resume/diagnose`（Task 2，無 body）。

- [ ] **Step 1: api.ts**

`sentinel/web/frontend/src/api.ts`：
(a) `ResumeState` interface 移除 `target_title` 與 `expected_salary` 兩行。
(b) 新增型別與函式：
```typescript
export interface JobPreferences {
  target_title: string;
  expected_salary: number | null;
  locations: string[];
  conditions: string[];
  avoid: string[];
}

export async function getPreferences(): Promise<JobPreferences> {
  const r = await fetch("/api/preferences");
  return r.json();
}

export async function putPreferences(p: JobPreferences): Promise<Response> {
  return fetch("/api/preferences", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(p),
  });
}
```
(c) `diagnoseResume` 改為無參數、不帶 body：
```typescript
export async function diagnoseResume(): Promise<Response> {
  return fetch("/api/resume/diagnose", { method: "POST" });
}
```

- [ ] **Step 2: ProfilePage 偏好區**

`sentinel/web/frontend/src/ProfilePage.tsx`：
- import 補 `Textarea`（@mantine/core）、`getPreferences`/`putPreferences`/`type JobPreferences`（./api）。
- 移除原本 seed `title`/`salary` 自 `resume.data`（GET /api/resume 已無這兩欄）的 `useEffect`。
- 新增偏好 query 與表單 state：
```typescript
  const prefs = useQuery({ queryKey: ["preferences"], queryFn: getPreferences });
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [locations, setLocations] = useState("");
  const [conditions, setConditions] = useState("");
  const [avoid, setAvoid] = useState("");
  const [prefBusy, setPrefBusy] = useState(false);
  const [prefErr, setPrefErr] = useState<string | null>(null);

  useEffect(() => {
    if (prefs.data) {
      setTitle(prefs.data.target_title);
      setSalary(prefs.data.expected_salary ?? "");
      setLocations(prefs.data.locations.join("\n"));
      setConditions(prefs.data.conditions.join("\n"));
      setAvoid(prefs.data.avoid.join("\n"));
    }
  }, [prefs.data]);

  function prefPayload(): JobPreferences {
    const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
    return {
      target_title: title.trim(),
      expected_salary: salary === "" ? null : Number(salary),
      locations: lines(locations), conditions: lines(conditions), avoid: lines(avoid),
    };
  }

  async function savePrefs() {
    setPrefErr(null); setPrefBusy(true);
    try {
      const r = await putPreferences(prefPayload());
      if (!r.ok) { setPrefErr("儲存失敗"); return; }
      qc.invalidateQueries({ queryKey: ["preferences"] });
    } catch { setPrefErr("網路錯誤，請重試"); }
    finally { setPrefBusy(false); }
  }
```
- `runDiagnose` 改為先存偏好再健檢（健檢無 body）：
```typescript
  async function runDiagnose() {
    setErr(null); setBusy(true);
    try {
      const pr = await putPreferences(prefPayload());
      if (!pr.ok) { setErr("儲存偏好失敗"); return; }
      qc.invalidateQueries({ queryKey: ["preferences"] });
      const r = await diagnoseResume();
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "健檢失敗"); return; }
      qc.invalidateQueries({ queryKey: ["resume"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }
```
- 版面：把原本履歷 `Paper` 內的「目標職稱/期望月薪」`Group` 與「執行健檢」按鈕**移到新的偏好 `Paper`**（放在履歷 `Paper` 之後、健檢結果 Grid 之前）。偏好 `Paper` 內容：
```tsx
        <Paper bg="dark.6" radius="md" p="lg">
          <Stack>
            <Text fw={600}>求職偏好</Text>
            <Group grow>
              <TextInput label="目標職稱" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
              <NumberInput label="期望月薪（選填）" value={salary} onChange={(v) => setSalary(typeof v === "number" ? v : "")} />
            </Group>
            <Textarea label="想要的工作地點（一行一個）" autosize minRows={2} value={locations} onChange={(e) => setLocations(e.currentTarget.value)} />
            <Textarea label="軟條件（一行一個，如 可遠端）" autosize minRows={2} value={conditions} onChange={(e) => setConditions(e.currentTarget.value)} />
            <Textarea label="避雷（一行一個，如 博弈）" autosize minRows={2} value={avoid} onChange={(e) => setAvoid(e.currentTarget.value)} />
            {prefErr && <Text c="danger.6" size="sm">{prefErr}</Text>}
            <Group>
              <Button variant="light" onClick={savePrefs} loading={prefBusy}>儲存偏好</Button>
              <Button onClick={runDiagnose} loading={busy} disabled={!resume.data?.has_resume || !title.trim()}>執行健檢</Button>
            </Group>
            {err && <Text c="danger.6" size="sm">{err}</Text>}
            <BusyHint active={busy} label="分析中" />
          </Stack>
        </Paper>
```
（履歷 `Paper` 內原本的「目標職稱/期望月薪/健檢/err/BusyHint」相關 JSX 與 state 使用要移除或搬過來，避免重複宣告與 unused。`d`（診斷結果）Grid 維持不變。）

- [ ] **Step 3: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功。若報 unused（搬移後殘留變數/import）清乾淨。

- [ ] **Step 4: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠。

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/ProfilePage.tsx
git commit -m "feat(sentinel): 我的履歷頁偏好區(目標/薪資/地點/條件/避雷)（SP19）"
```

---

## Self-Review 註記（計畫作者）

- **Spec coverage：** JobPreferences+欄+遷移+端點(Task1)、讀取點切換+移欄+測試更新(Task2)、前端偏好區(Task3) 全覆蓋。
- **常綠策略：** Task1 只加儲存與端點、不動讀取點 → 套件不受影響；Task2 原子化切換+移欄+一次更新所有破掉測試 → 完成閘=全套件綠；Task3 前端獨立。
- **is_watched/keywords 不動：** 三個任務都不碰 watch.py/Settings.watched_keywords/SettingsModal。
- **測試面：** 已列出 7 個受影響測試檔的精確改法；Pydantic v2 建構未定義欄位會 raise → 所有 `ResumeState(target_title=...)` 建構點必清（Task2 Step4 已逐一點名 test_chat/test_chat_apply/test_web_match/test_resume_store/test_web_app/test_web_chat/test_web_resume）。
- **型別一致：** `JobPreferences`(api.ts) 對應後端欄位；`diagnoseResume` 改無參數與 Task2 diagnose 無 body 一致；`getPreferences`/`putPreferences` 對應 Task1 端點。
- **遷移安全：** raw-JSON 冪等，`test_migrate_*` 三個測試覆蓋 copy/idempotent/noop。
