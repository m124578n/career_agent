# 面試紀錄 設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

讓使用者為追蹤中的職缺**手動記錄多筆面試紀錄（時間＋內容）**，從儀表板卡片（JobCardDrawer）編輯；agent 也能在對話中經**確認卡**幫忙記一筆。比照 SP20 offer_json 的持久化樣式。

## 目標

一句話：**在 `TrackedJob` 加 `interviews_json`（多筆 `{when, content}`），JobCardDrawer 加「面試紀錄」編輯區（PUT 整列），並讓 agent 用 `interview_note` 確認卡 append 一筆。**

## 現況（實作依據）

- **`TrackedJob`（models.py:192）**：code(PK)/company/title/url/salary/state/match_score/match_json/tailor_json/**offer_json**/created_at/updated_at。SP20 的 offer_json 已示範「加欄＋冪等 migration＋set_tracked_state 建列」的樣式。
- **store（store.py）**：`_SCHEMA` tracked_jobs；`_migrate`（`PRAGMA table_info` + 冪等 `ALTER ... ADD COLUMN`，現含 match_json/tailor_json/offer_json）；`load_tracked_jobs`/`get_tracked_job`/`upsert_tracked_job`（含各 json 欄）；`set_tracked_state`（建列或更新、保留既有欄位）。
- **apply_update（chat.py）**：管道動作 `track/job_offer/job_reject/job_reset/untrack`（走 payload→store，ALLOWED 白名單）；`tailor/negotiate` 不走 apply_update（前端直打端點）。
- **JobCardDrawer.tsx**：開啟時 `getTrackedJob(code)` 載入 state/match/tailor/offer；有比對/研究/客製化/狀態區。CardJob = {code, company, title, url, salary}。已投遞等各狀態卡片點列都會開此 Drawer。
- **ChatPage SuggestionCard**：`PIPE_FIELDS`（track/job_offer/...）走 SuggestionCard，label 讀 payload，apply 成功後 invalidate snapshot；`FIELD_LABEL` 中文標籤表。
- **`GET/PUT /api/tracked`、`/api/tracked/{code}`（app.py）**：既有 tracked CRUD。

## 資料模型（models.py）

```python
class InterviewNote(BaseModel):
    when: str = ""      # 面試時間（自由字串，如 "2026-07-10 14:00 一面"）
    content: str = ""   # 面試內容/心得
```

`TrackedJob` 加（在 offer_json 之後）：

```python
    interviews_json: str = ""   # 序列化的 list[InterviewNote]
```

## 後端變更

### 1. store：migration ＋ 欄位 ＋ 兩個 helper

- `_SCHEMA` tracked_jobs 加一行 `interviews_json TEXT NOT NULL DEFAULT ''`（tailor_json/offer_json 行後補逗號）。
- `_migrate` 欄位迴圈加 `"interviews_json"`：`for col in ("match_json", "tailor_json", "offer_json", "interviews_json"):`。
- `load_tracked_jobs`/`get_tracked_job`/`upsert_tracked_job` 的 SELECT/解構/建構/INSERT 全部補 `interviews_json`（比照 offer_json，`or ""` NULL-guard）。
- 兩個 helper（`InterviewNote` import 進 store.py models import）：

```python
def set_interviews(conn: sqlite3.Connection, code: str, notes: list[InterviewNote]) -> None:
    """整列取代某職缺的面試紀錄；不存在則建列。保留其他欄位。"""
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
    """附加一筆面試紀錄（agent 用）。"""
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

### 2. 端點（web/app.py，import `InterviewNote`）

- `GET /api/tracked/{code}` 回傳加 `"interviews"`：
  ```python
  "interviews": json.loads(tj.interviews_json) if tj.interviews_json else [],
  ```
  found=False 分支加 `"interviews": []`。
- `PUT /api/tracked/{code}/interviews`（卡片編輯，整列取代）：
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

### 3. apply_update：`interview_note`（agent append，chat.py）

- `ALLOWED` 加 `"interview_note": {"set"}`。
- `apply_update` 加分支（在管道動作分支附近）：
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

### 4. 聊天合約（chat.py `_CONTRACT`）

- 範例加：`{"field": "interview_note", "op": "set", "payload": {"code": "abc12", "when": "2026-07-10 14:00 一面", "content": "問了系統設計與過往專案"}}`。
- 規則補述：`interview_note`＝使用者描述某職缺的面試（時間、問了什麼、心得）時，提議記一筆；payload.code 必來自 get_pipeline/search_jobs 實際結果、不得杜撰；只提議，按下確認才記。

## 前端變更

### 5. api.ts

- `InterviewNote` 型別 `{ when: string; content: string }`。
- `TrackedCard`（getTrackedJob 回傳型別）加 `interviews: InterviewNote[]`。
- `setInterviews(code, notes): Promise<Response>`（`PUT /api/tracked/{code}/interviews`，body `{notes}`）。

### 6. JobCardDrawer「面試紀錄」區

- 開啟時 `getTrackedJob` 的 `interviews` 載進 local state（`notes: InterviewNote[]`），依 `when` 升冪顯示。
- 新增「面試紀錄」`Paper`：
  - 現有紀錄列表：每筆顯示 `when`（teal/mono）＋ `content`（whitespace pre-wrap），附「刪除」ActionIcon。
  - 新增表單：`TextInput`（時間，placeholder「2026-07-10 14:00 一面」）＋ `Textarea`（內容）＋「新增」按鈕 → append 到 local `notes` → `setInterviews(code, notes)` → 成功 invalidate snapshot、清表單。
  - 刪除某筆 → 從 local `notes` 移除 → `setInterviews` → invalidate。
  - 無 code（`!job.code`）→ 顯示「此職缺無代碼，無法記錄面試」。
- 所有呼叫檢查 `r.ok`（比照既有慣例）。

### 7. ChatPage：interview_note 卡（走既有 SuggestionCard）

- `FIELD_LABEL` 加 `interview_note: "面試紀錄"`。
- `PIPE_FIELDS` 加 `"interview_note"`（→ 成功後 invalidate snapshot；label 走 pipe 分支）。
- SuggestionCard 的 pipe label 對 interview_note 顯示 `${payload.when ?? ""}：${payload.content ?? ""}`（截斷過長）。其餘既有卡片行為不變。

## Global Constraints（實作時必守）

- **需 code**：面試紀錄以 tracked_jobs（code PK）持久化；無 code 的職缺不可記（卡片提示、apply_update 回 ok=False）。
- **建列 or 更新、保留欄位**：`set_interviews`/`add_interview_note` 對不存在的 code 建 tracked 列、存在則只更新 interviews_json＋updated_at，不動其他欄位（尤其 state/offer_json）。
- **兩條寫入語意**：卡片編輯走 `PUT`（整列取代）；agent 走 `apply_update interview_note`（append 一筆）。互不干擾。
- **相容加法式**：`interviews_json`/`InterviewNote`/`interviews` 皆加法；`_migrate` 冪等 ALTER 不丟資料；既有 tracked CRUD、offer/match/tailor、SSE、卡片行為不變。
- **韌性**：壞 interviews_json 解析 try/except → 視為空列，不整批消失。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 127.0.0.1；前端 `npm run build` 必過。

## 測試策略（後端用專案 venv）

- **store**：
  - `set_interviews` 建列（不存在的 code）→ get 回該 interviews_json round-trip；對既有 job 只改 interviews、不動 state/offer_json。
  - `add_interview_note` append（既有兩筆→三筆）；對不存在 code 建列含一筆；壞 interviews_json → 視為空、append 成一筆。
  - migration：舊表（缺 interviews_json）connect 後補欄、不丟資料。
- **端點**：`GET /api/tracked/{code}` 回 interviews；`PUT .../interviews` 整列取代（GET 讀回相同）；空 code 400。
- **apply_update**：`interview_note` payload{code,when,content} → get_tracked_job 的 interviews 出現該筆；缺 code → ok=False。`ALLOWED` 含 interview_note。
- **合約**：`build_system_prompt` 含 `interview_note`。
- **前端**：無單元測試，靠 `npm run build` ＋人工（卡片新增/刪除面試紀錄、agent 記一筆）。

## 明確不做（Out of Scope）

- 與 104 面試訊號（snapshot.interviews）自動關聯/去重。
- 面試提醒/行事曆（已有 Google 日曆連結）。
- 面試紀錄的結構化欄位（關卡/面試官/結果）→ 先自由文字（when + content）。
- 把 interviews 帶進 PipelineJob 於儀表板列顯示（卡片內即可；儀表板列不改）。
