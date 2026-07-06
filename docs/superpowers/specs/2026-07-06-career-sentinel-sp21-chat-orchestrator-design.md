# SP21：聊天當總指揮（第一階段）設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 求職流水線的收尾壓軸（第一階段）。把聊天從「整理助手」（只整理履歷/偏好/記憶）升級為「求職總指揮」：agent **看得懂整條求職管道**、能自動搜尋/讀取，並以**確認卡**提議輕量動作（追蹤/設狀態/設 offer/取消追蹤）。花 LLM 錢的動作（比對/客製化/研究）留給下一階段。

roadmap：SP15 ✅ → SP16 ✅ → SP17 ✅ → SP18 ✅ → SP19 ✅ → SP20 ✅ → **SP21（本篇）聊天當總指揮·第一階段** → SP21b（未來）比對/客製化/研究接進聊天 → SP22（未來）offer 談判建議。

## 目標

一句話：**在聊天系統提示注入整條管道脈絡、加一個 `get_pipeline` 讀取工具，並讓 agent 用既有 `<suggestions>` 確認卡機制提議「不花 LLM 錢」的管道動作（追蹤/設 offer/未錄取/重設/取消追蹤），由使用者一鍵確認後執行。**

## 現況（實作依據）

- **`chat.py`**：
  - `build_system_prompt(resume, settings, prefs, memory) -> str`（48）：組裝狀態摘要（目標/薪資/偏好/關注/記憶）＋履歷全文＋工具說明（目前只提 `search_jobs`）＋`_CONTRACT`（`<suggestions>` 規則）。
  - `_CONTRACT`（23）：定義 `<suggestions>` 建議區塊格式與允許的 field/op（target_title/expected_salary/locations/conditions/avoid/watched_*/resume_text/memory）。
  - `SuggestedUpdate`（models.py:232）：`field`/`op`/`value`/`old`/`new`。**無結構化 payload 欄位。**
  - `ALLOWED`（141）＋`apply_update(conn, upd)`（167）：白名單校驗＋逐 field 套用（寫 prefs/settings/resume/memory）。
  - `TOOLS`（313）：目前只有 `search_jobs`；`_execute_search`（324）執行；`stream_with_tools(messages, *, system, client, feature)`（341）：Foundry 原生 tool use 迴圈，`TOOL_LOOP_MAX = 2`（19），硬寫死讀 `keyword` 呼叫 `_execute_search`。
- **`web/app.py`**：
  - `/api/chat`（342）：`build_system_prompt(...)` 組 system（346）→ `_chat_events(messages, system)`（44/360）→ foundry 走 `stream_with_tools`。SSE 事件：`delta`（文字）、`jobs`（搜尋結果）、`suggestions`（`field != "memory"` 的建議卡）、`remembered`/`forgot`（memory 自動套用）、`done`/`error`。
  - `/api/chat/apply`（409）：`chat_apply(upd: SuggestedUpdate)` → `apply_update`。
  - `create_app(db_path)`（102）：`resolved_db`（104）＋`_conn()`（106，每次開新連線，thread-safe）。
  - 已 import `OfferDetail`、`TrackedJob`、`pipeline`、`store`。
- **`pipeline.build_pipeline(conn) -> list[PipelineJob]`**：純讀 best-effort（try/except → []）；`PipelineJob` 有 `code/company/title/state/salary/match_score/when/location/offer/...`。
- **前端 `ChatPage.tsx`**：`FIELD_LABEL`（30）中文標籤表；`SuggestionCard`（41）依 `op` 組 label（`replace_snippet`/`append_section`/預設 `→ value`）→ 按套用呼叫 `applyUpdate(s)`（`/api/chat/apply`）。`suggestions` 事件 → 渲染卡片。`jobs` 事件 → `JobRow`。
- **`api.ts`**：`SuggestedUpdate`（198）`{field, op, value, old, new}`——**無 payload**。`applyUpdate(u)`（221）。

## 資料模型

### `SuggestedUpdate` 加 `payload`（models.py）

```python
class SuggestedUpdate(BaseModel):
    field: str
    op: str = "set"
    value: str | int | list[str] | None = None
    old: str | None = None
    new: str | None = None
    payload: dict | None = None   # 管道動作的結構化資料（code + 動作參數）
```

加法式（Pydantic v2 忽略舊 JSON 無此欄）。既有 field/op 不受影響。

## 後端變更

### 1. 管道脈絡摘要（`chat.py` 純函式）

```python
_PIPE_GROUP_LIMIT = 5  # 每組摘要最多列幾筆

def format_pipeline_summary(jobs: list["PipelineJob"]) -> str:
    """把 build_pipeline 的結果壓成給 system prompt 的精簡摘要（含 code 供 agent 引用）。空則回 ''。"""
```

- 依 `state` 分組（interviewing/offer/applied/tailored/matched/interested/rejected），每組列「計數」＋前 `_PIPE_GROUP_LIMIT` 筆：`公司 · 職稱（code）` ＋該狀態關鍵欄（interviewing 帶 `when`、offer 帶年薪/月薪）。全空回 `""`。
- 純顯示、唯讀；不呼叫 LLM。

`build_system_prompt` 加一個參數（預設空字串，向後相容）：

```python
def build_system_prompt(
    resume, settings, prefs, memory, pipeline_summary: str = "",
) -> str:
```

- head 在「長期記憶」之後、履歷之前插入「目前求職管道」段（`pipeline_summary or "（管道目前無職缺）"`）。
- 工具說明段改為同時介紹 `search_jobs` 與 `get_pipeline`（「要看你目前管道細節時用 `get_pipeline`」）。
- `_CONTRACT` 擴充（見 §4 提示合約）。

### 2. `get_pipeline` 讀取工具 ＋ 多工具分派（`chat.py`）

`TOOLS` 加一項：

```python
{
    "name": "get_pipeline",
    "description": "讀取使用者目前的求職管道（各狀態職缺、offer 明細、面試時間、job code）。要引用或操作既有職缺前先用它確認 code 與現況。",
    "input_schema": {"type": "object", "properties": {}},
}
```

`TOOL_LOOP_MAX` 2 → **4**（讓「先 get_pipeline 再回答/提議」的多步編排可行）。

`stream_with_tools` 加 `db_path: str | None = None` 參數；把硬寫死的 `_execute_search` 分派抽成 `_execute_tool(name, tool_input, db_path)`：

```python
def _execute_tool(name: str, tool_input: dict, db_path: str | None):
    """回 (event_dict_or_None, result_text, is_error)。event 供 yield 給前端（如 jobs）。"""
    if name == "search_jobs":
        jobs, result_text, is_error = _execute_search(str(tool_input.get("keyword", "")))
        event = {"type": "jobs", "keyword": str(tool_input.get("keyword", "")), "items": jobs} if not is_error else None
        return event, result_text, is_error
    if name == "get_pipeline":
        return None, _pipeline_tool_json(db_path), False
    return None, f"未知工具：{name}", True


def _pipeline_tool_json(db_path: str | None) -> str:
    """get_pipeline 執行體：開新連線讀管道，回精簡 JSON（唯讀 best-effort）。"""
    if not db_path:
        return "[]"
    try:
        conn = store.connect(db_path)
        jobs = pipeline.build_pipeline(conn)
    except Exception:
        return "[]"
    brief = [
        {"code": j.code, "company": j.company, "title": j.title, "state": j.state,
         "salary": j.salary, "match_score": j.match_score, "when": j.when,
         "offer": j.offer.model_dump() if j.offer else None}
        for j in jobs
    ]
    return json.dumps(brief, ensure_ascii=False)
```

- `stream_with_tools` 迴圈裡把 `_execute_search(keyword)` 那段換成通用分派：對每個 `tool_use` block 取 `block.name` 與 `block.input`，呼叫 `_execute_tool(...)`；有 event 就 `yield`（維持既有 `jobs` 事件行為），組 `tool_result`。
- get_pipeline 開自己的短命連線（thread-safe，比照 app.py `gconn` 慣例），唯讀、失敗回 `[]`，**絕不 mutation**。
- `pipeline`/`store` 已在 chat.py 可用（`store` 已 import；`pipeline` 需 import：`from . import ... pipeline ...`）。

### 3. 管道動作（確認卡，`ALLOWED` ＋ `apply_update`）

`ALLOWED` 加五個 field（op 統一 `set`）：

```python
    "track": {"set"},
    "job_offer": {"set"},
    "job_reject": {"set"},
    "job_reset": {"set"},
    "untrack": {"set"},
```

`apply_update` 加對應分支（讀 `upd.payload`；缺 code 一律 `ApplyResult(ok=False, ...)`）：

```python
    if upd.field in ("track", "job_offer", "job_reject", "job_reset", "untrack"):
        payload = upd.payload or {}
        code = str(payload.get("code", "")).strip()
        if not code:
            return ApplyResult(ok=False, message="缺少職缺代碼")
        if upd.field == "track":
            store.merge_tracked_job(
                conn, code, state="interested",
                company=str(payload.get("company", "")), title=str(payload.get("title", "")),
                url=str(payload.get("url", "")), salary=str(payload.get("salary", "")),
            )
            return ApplyResult(ok=True)
        if upd.field == "job_offer":
            from .models import OfferDetail
            offer = OfferDetail(
                salary_year=payload.get("salary_year"), salary_month=payload.get("salary_month"),
                location=str(payload.get("location", "")), level=str(payload.get("level", "")),
                start_date=str(payload.get("start_date", "")), notes=str(payload.get("notes", "")),
            )
            store.set_tracked_state(conn, code, "offer", offer=offer)
            return ApplyResult(ok=True)
        if upd.field == "job_reject":
            store.set_tracked_state(conn, code, "rejected")
            return ApplyResult(ok=True)
        if upd.field == "job_reset":
            store.set_tracked_state(conn, code, "interested")
            return ApplyResult(ok=True)
        # untrack
        store.delete_tracked_job(conn, code)
        return ApplyResult(ok=True)
```

- 放在既有 field 分支之後、memory 分支之前（memory 分支目前是函式尾端的無條件路徑，需改為明確 `if upd.field == "memory"` 或把管道分支插在 memory 之前 return，確保不誤落 memory）。**實作時把 memory 段改成明確 `if upd.field == "memory":` 條件**，避免新 field 落到 memory 邏輯。
- `OfferDetail` 的 `salary_year`/`salary_month` 由 Pydantic 驗證（非數字→ValidationError；為穩健，payload 傳入前端已確保為 number|null；後端 `int|None` 欄位對非法值會拋，apply 外層 `/api/chat/apply` 既有 try 由 FastAPI 處理，但為一致性可包 try 回 ApplyResult——見測試）。

### 4. 提示合約擴充（`_CONTRACT` / build_system_prompt，`chat.py`）

在 `_CONTRACT` 的允許清單與範例加入管道動作，並明確「**提議、不自行執行**」：

- 新增可用 field/op（附 payload 範例）：
  - `track`/set（payload: `{code, company, title, url, salary}`）：把職缺加入管道（追蹤）。
  - `job_offer`/set（payload: `{code, salary_year?, salary_month?, location?, level?, start_date?, notes?}`；**年薪/月薪為整數，使用者說年薪就填 salary_year**）：標記錄取並記 offer 明細。
  - `job_reject`/set、`job_reset`/set、`untrack`/set（payload: `{code, company?}`；company 僅供顯示）。
- 規則補述：這些管道動作**一律以 `<suggestions>` 提議、由使用者確認後才生效，agent 不得聲稱已完成**；code 必須來自 `get_pipeline` 或 `search_jobs` 的實際結果，不得杜撰；一次提議可含多筆 items。

### 5. app.py 接線

`/api/chat` 組 system 處（346）改為先算管道摘要再傳入：

```python
        conn = _conn()
        try:
            pipe_summary = chatmod.format_pipeline_summary(pipeline.build_pipeline(conn))
        except Exception:
            pipe_summary = ""
        system = chatmod.build_system_prompt(
            store.load_resume(conn), store.load_settings(conn),
            store.load_preferences(conn), store.load_memory(conn), pipe_summary,
        )
```

`_chat_events(messages, system)` 加 `db_path` 傳遞給 `stream_with_tools`：

```python
def _chat_events(messages, system, db_path=None):
    if config.llm_provider() == "foundry":
        yield from chatmod.stream_with_tools(messages, system=system, db_path=db_path)
    else:
        for chunk in llm.chat_stream(messages, system=system, feature="整理助手"):
            yield {"type": "text", "text": chunk}
```

呼叫端（360）改 `_chat_events(messages, system, resolved_db)`。

管道動作卡走既有 `suggestions` 事件路徑（`field != "memory"` → cards），無需改 SSE 骨架。

## 前端變更

### 6. api.ts

`SuggestedUpdate` 型別加 `payload?: Record<string, unknown> | null`。

### 7. ChatPage 確認卡渲染（`ChatPage.tsx`）

- `FIELD_LABEL` 加：`track: "追蹤"`, `job_offer: "標記錄取"`, `job_reject: "標記未錄取"`, `job_reset: "重設狀態"`, `untrack: "取消追蹤"`。
- `SuggestionCard` 的 label 計算加管道動作分支（讀 `s.payload`）：
  - `track` → `${payload.company} · ${payload.title}`
  - `job_offer` → `${payload.company}${payload.salary_year ? ` · 年薪 ${payload.salary_year}` : payload.salary_month ? ` · 月薪 ${payload.salary_month}` : ""}`
  - `job_reject`/`job_reset`/`untrack` → `${payload.company || payload.code}`
  - 其餘沿用既有 value/old/new 邏輯。
- `SuggestionCard.apply` 成功後，若 `s.field` 屬管道動作集合，`qc.invalidateQueries({ queryKey: ["snapshot"] })`（讓 Dashboard 即時反映）。既有非管道欄位行為不變。

## Global Constraints（實作時必守）

- **mutation 只走確認卡**：所有改狀態/管道的動作（track/job_offer/job_reject/job_reset/untrack）一律經 `<suggestions>` 卡 → 使用者按套用 → `/api/chat/apply` → `apply_update`。**agent 絕不在工具迴圈裡執行 mutation**；工具迴圈只有唯讀的 `search_jobs`/`get_pipeline`。
- **本階段不接 LLM 花錢動作**：比對/客製化/研究不進聊天工具或動作卡（留 SP21b）。
- **管道脈絡 best-effort**：`format_pipeline_summary` 吃 `build_pipeline`（try/except → []）；app.py 端再包 try，失敗則 `pipe_summary=""`，聊天照常運作、絕不中斷。
- **memory 分支明確化**：`apply_update` 尾端的 memory 邏輯改成明確 `if upd.field == "memory":`，確保新管道 field 不誤落 memory 路徑。
- **code 不杜撰**：提示合約要求 agent 的 payload.code 必來自 `get_pipeline`/`search_jobs` 實際結果。
- **相容加法式**：`SuggestedUpdate.payload` 加法（舊 JSON 無此欄→None）；既有 field/op/卡片行為不變；memory 自動套用、非管道建議卡渲染皆不變。
- **token 控制**：`format_pipeline_summary` 每組至多 `_PIPE_GROUP_LIMIT` 筆＋計數；`get_pipeline` 回精簡 JSON（不含 raw）。
- **PII/安全**：本 SP 無新增外部呼叫（除既有 `search_jobs`）；`get_pipeline` 只讀本機 SQLite。不寫入 104。後端綁 `127.0.0.1`。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`（set_tracked_state/merge_tracked_job 既有）。
- 後端測試用專案 venv `sentinel/.venv/Scripts/python.exe -m pytest -q`；前端 `npm run build` 必過。

## 測試策略

- **`format_pipeline_summary`**（純函式）：多狀態 job → 含各組計數與 code；每組超過 `_PIPE_GROUP_LIMIT` 只列上限；offer 帶年薪、interviewing 帶 when；空清單 → `""`。
- **`build_system_prompt`**：傳入 pipeline_summary → head 含「目前求職管道」段與該摘要；工具說明含 `get_pipeline`；空摘要 → 顯示「（管道目前無職缺）」。
- **`_pipeline_tool_json`**：mock db_path＋建幾筆 tracked/pipeline → 回含 code/state/offer 的 JSON；`db_path=None` → `"[]"`；build 失敗 → `"[]"`。
- **`_execute_tool` 分派**：`search_jobs`（mock `_execute_search`）回 jobs event；`get_pipeline` 回 pipeline JSON、event=None；未知工具 → is_error。
- **`apply_update` 管道動作**（用 tmp_path conn）：
  - `track` → `get_tracked_job` 出現、state interested、帶 company/title/url/salary。
  - `job_offer`（payload 含 salary_year/location）→ state offer、offer_json round-trip。
  - `job_reject` → state rejected、offer_json 空；`job_reset` → interested；`untrack` → 該 code 消失。
  - 缺 code → `ok=False`「缺少職缺代碼」。
  - 對已存在 offer 職缺送 track（merge）→ 防降級：state 仍 offer、offer_json 保留（回歸 SP20 修正）。
- **`ALLOWED` 白名單**：`apply_update` 對未允許 field/op → `ok=False`「不允許…」。
- **`SuggestedUpdate` payload**：`parse_suggestions` 解析含 payload 的 `<suggestions>` → payload 正確帶入；無 payload 舊格式仍可解析。
- **memory 分支明確化回歸**：既有 memory remember/forget 測試維持綠（改成明確 `if` 後不回歸）。
- **前端**：無單元測試，靠 `npm run build` ＋人工；契約由後端測試守。

## 明確不做（Out of Scope）

- 比對/客製化/研究接進聊天（LLM 花錢動作）→ **SP21b（未來）**。
- offer 談判建議 → SP22。
- agent 自動（不確認）執行任何 mutation。
- 多輪自主 agent、背景排程觸發聊天動作。
- 既有 UI/UX 精修。
