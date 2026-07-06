# SP19：偏好集中 設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 求職流水線第五個子專案。把散落的求職偏好——目標職稱（`target_title`）、期望薪資（`expected_salary`，原在 `ResumeState`）——收進單一 `JobPreferences` 模型（已有 `locations/conditions/avoid`），並在「我的履歷」頁下半新增偏好編輯區。**目標/薪資/地點級**：`keywords`（原 `Settings.watched_keywords`）因與 `is_watched` 高亮邏輯綁定、風險高，**留在 Settings 不動**。

roadmap：SP15 ✅ → SP16 ✅ → SP17 ✅ → SP18 ✅ → **SP19（本篇）偏好集中** → SP20 offer 比較 → SP21 聊天當總指揮。

## 目標

一句話：**把 `target_title`／`expected_salary` 從 `ResumeState` 搬進 `JobPreferences`，成為與 `locations/conditions/avoid` 同一個「偏好」單一來源，並在我的履歷頁提供偏好編輯 UI。**

## 現況（實作依據）

- **`JobPreferences`（models.py:177）**：`locations`、`conditions`、`avoid`（皆 `list[str]`）。單列 JSON 存（`store.load_preferences`/`save_preferences`）。**目前沒有 REST 端點**——只能透過聊天 `apply_update` 編輯（`chat.py`）。
- **`ResumeState`**：`resume_text`、`target_title`、`expected_salary`、`diagnosis`、`source`。
- **target_title / expected_salary 讀寫點**：
  - `POST /api/resume/diagnose`（app.py:176-190）：收 `_DiagnoseReq{target_title, expected_salary}`，`diagnosis.diagnose(resume_text, req.target_title, req.expected_salary)`，寫 `state.target_title/expected_salary/diagnosis`。
  - `GET /api/resume`（app.py:218-219）：回 `target_title`、`expected_salary`。
  - `POST /api/match`（app.py:239）：`match.match(resume_text, state.target_title or "（未指定）", jd)`。
  - `POST /api/tailor`（app.py:266）：`tailor.tailor_application(resume_text, state.target_title or "（未指定）", jd)`。
  - `chat.py`：`build_system_prompt`（56-57）與 `render`（292-293）讀 `resume.target_title/expected_salary`；`apply_update`（171-179）把 `target_title`/`expected_salary` 寫進 `ResumeState`。
  - `match.py`/`tailor.py`/`diagnosis.py`：純 prompt builder，`target_title` 由 web 層以參數傳入，**不直接讀 model**（不需改）。
- **keywords（不動）**：`Settings.watched_keywords`；`watch.is_watched(company, haystack, settings)`（watch.py:14）用它高亮，被 snapshot 各處呼叫約十次；`SettingsModal.tsx` 編輯之。**SP19 全部保持原狀。**
- **前端**：`ProfilePage.tsx`（SP18）現有 `目標職稱`/`期望月薪` `TextInput`/`NumberInput`（seed 自 `GET /api/resume`）＋健檢；偏好的 `locations/conditions/avoid` 目前無 UI。

## 資料模型

### `JobPreferences` 加兩欄（models.py）

```python
class JobPreferences(BaseModel):
    target_title: str = ""
    expected_salary: int | None = None
    locations: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
```

### `ResumeState` 移除兩欄（models.py）

```python
class ResumeState(BaseModel):
    resume_text: str = ""
    diagnosis: ResumeDiagnosis | None = None
    source: str = ""
```

Pydantic v2 預設忽略多餘欄位（`model_validate_json` 對含 `target_title` 的舊 JSON 不報錯，靜默丟棄），故移除欄位不炸既有 DB。

### 遷移（`store.py`，raw-JSON 層、冪等）

`connect()` 內（`executescript(_SCHEMA)` 之後）呼叫 `_migrate_preferences(conn)`：**在模型丟棄欄位之前**直接讀 raw JSON 搬移。

```python
def _migrate_preferences(conn: sqlite3.Connection) -> None:
    """把舊 ResumeState 的 target_title/expected_salary 搬進 JobPreferences（冪等）。"""
    pref_row = conn.execute("SELECT data FROM preferences WHERE id = 1").fetchone()
    res_row = conn.execute("SELECT data FROM resume WHERE id = 1").fetchone()
    if res_row is None:
        return
    resume = json.loads(res_row[0])
    old_title = resume.get("target_title") or ""
    old_salary = resume.get("expected_salary")
    if not old_title and old_salary is None:
        return
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

- 冪等：prefs 已有 target_title 就不覆寫；跑幾次都安全。
- 不修改 resume 表（其多餘 key 由模型載入時自動忽略；下次 `save_resume` 自然寫出不含這兩欄的 JSON）。

## 後端變更

### 新 `GET / PUT /api/preferences`（web/app.py）

```python
@app.get("/api/preferences")
def get_preferences() -> dict:
    return store.load_preferences(_conn()).model_dump()

@app.put("/api/preferences")
def put_preferences(prefs: JobPreferences) -> dict:
    store.save_preferences(_conn(), prefs)
    return prefs.model_dump()
```

（`JobPreferences` 需 import 進 app.py 的 models import 清單。）

### 讀取點改指 `JobPreferences`

- **`POST /api/resume/diagnose`**：改為從 prefs 讀 target/salary，不再收 `_DiagnoseReq`：
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
  移除 `_DiagnoseReq` 模型（grep 確認無他處引用）。
- **`GET /api/resume`**：移除回傳的 `target_title`/`expected_salary`（改由 `/api/preferences` 提供）。保留 `has_resume/chars/diagnosis/source`。
- **`POST /api/match`**：`state.target_title` → `store.load_preferences(conn).target_title`。
- **`POST /api/tailor`**：同上。
- **`chat.py`**：
  - `build_system_prompt`（56-57）與 `render`（292-293）：`resume.target_title/expected_salary` → `prefs.target_title/expected_salary`（兩函式都已收 `prefs` 參數）。
  - `apply_update`（171-179）：`target_title`/`expected_salary` 的寫入從 `ResumeState` 改為 `JobPreferences`（`load_preferences`→改欄位→`save_preferences`），與既有 `locations/conditions/avoid` 同路徑。`ALLOWED`/白名單（chat.py:142-143）維持（field 名不變、只換儲存目標）。

## 前端變更

### 偏好區（`ProfilePage.tsx` 下半）＋ api.ts

- **api.ts**：
  - `ResumeState` 型別移除 `target_title`/`expected_salary`。
  - 新 `JobPreferences` 型別：`{ target_title: string; expected_salary: number | null; locations: string[]; conditions: string[]; avoid: string[] }`。
  - 新 `getPreferences(): Promise<JobPreferences>`、`putPreferences(p: JobPreferences): Promise<Response>`。
  - `diagnoseResume` 改為無參數 `POST /api/resume/diagnose`（不再送 target/salary）。
- **ProfilePage**：把現有 `目標職稱`/`期望月薪` 從履歷區移到新的**偏好區**（一個 `Paper`），並加 `地點`／`軟條件`／`避雷`（各一個 `Textarea`，一行一項，比照 SettingsModal 的 join/split 慣例）。
  - 偏好區 seed 自 `GET /api/preferences`。
  - 「儲存偏好」按鈕 → `PUT /api/preferences`（invalidate `preferences`）。
  - 「執行健檢」按鈕：先 `PUT /api/preferences`（存目前偏好表單值，確保 target_title 已存）再 `POST /api/resume/diagnose`（讀 prefs）→ 顯示優勢/待補強。`disabled` 條件改為 `!has_resume || !title.trim()`（title 取偏好表單的 target_title）。
- 視覺沿用既有 `Paper bg="dark.6"`／`Textarea`／`BusyHint`。

## Global Constraints（實作時必守）

- **is_watched / keywords 完全不動**：`watch.is_watched`、`Settings.watched_keywords`、`SettingsModal`、snapshot 的 is_watched 呼叫全部保持原狀（本 SP 不碰高亮/關注機制）。
- **遷移不丟資料、冪等**：`_migrate_preferences` 在 raw-JSON 層把舊 `ResumeState.target_title/expected_salary` 搬進 prefs（prefs 已有就不覆寫），跑幾次安全；既有使用者升級後目標職稱/薪資不消失。
- **單一來源**：搬移後 `target_title`/`expected_salary` 只存在於 `JobPreferences`；比對/客製化/健檢/聊天全讀 prefs。`ResumeState` 不再有這兩欄。
- **相容**：`ResumeState` 移欄靠 Pydantic 忽略多餘 key（不炸舊 JSON）；`/api/match`/`/api/tailor`/`/api/resume/upload`/`/api/resume/import104` 回傳不變（只換 target_title 來源）；聊天 `apply_update` 的 field 名（target_title/expected_salary）不變、只換儲存目標。
- 時間戳／後端綁 `127.0.0.1` 沿用；前端 `npm run build` 必過。

## 測試策略

- **遷移** `_migrate_preferences`：
  - 舊 DB：resume JSON 有 target_title/expected_salary、prefs 空 → connect 後 `load_preferences().target_title/expected_salary` 有值。
  - 冪等：prefs 已有 target_title → 不被 resume 的舊值覆寫；跑兩次結果一致。
  - resume 無舊值 → prefs 不變。
- **`GET/PUT /api/preferences`**：PUT 一組偏好 → GET 回相同；含 target_title/expected_salary/locations/conditions/avoid round-trip。
- **`POST /api/resume/diagnose`**（mock `diagnosis.diagnose`）：prefs 有 target_title＋有履歷 → 用 prefs.target_title 健檢、寫 diagnosis；prefs 無 target_title → 400；無履歷 → 400。
- **`POST /api/match`/`/api/tailor`**（既有測試）：改讀 prefs.target_title 後仍通過（必要時把測試的 target_title 設定改為經 `/api/preferences` 或直接 `save_preferences`）。
- **`GET /api/resume`**：不再含 target_title/expected_salary。
- **chat**：`apply_update` 對 `target_title`/`expected_salary` 寫進 `JobPreferences`（`load_preferences` 讀得到）；build_system_prompt 讀 prefs（既有 chat 測試相應調整）。
- **前端**：無單元測試，靠 `npm run build` ＋人工；契約由後端測試守。

## 明確不做（Out of Scope）

- keywords（watched_keywords）搬移、is_watched 改動 → 不做（風險高，留給未來若需要）。
- offer 比較 → SP20；聊天當總指揮 → SP21。
- 累積技術債 Minor（SP17 app.py 死 import/卡片 prefill r.ok/空 Anchor、SP18 Resume104Import 未強型別）——可本 SP 開場順手清或獨立 commit。
- 既有 UI/UX 精修。
