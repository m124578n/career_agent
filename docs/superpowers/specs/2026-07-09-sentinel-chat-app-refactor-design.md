# sentinel `chat.py` / `web/app.py` 依職責拆檔 — 設計

**日期**：2026-07-09
**範圍**：`sentinel/` 子專案；純內部重構，行為零改變。

## 目標與動機

`sentinel` 架構健檢發現兩個過大、多職責的檔案，是 AI 友善度的主要瓶頸：

- `src/career_sentinel/chat.py`（659 行）混了約 7 種職責：系統提示組裝、串流過濾、`apply_update`、對話壓縮＋記憶整理、匯出 MD、工具定義＋執行、tool-use 編排。
- `src/career_sentinel/web/app.py`（619 行）把 30 個 endpoint 全塞在單一 `create_app` 閉包。

把它們依既有職責縫線拆成聚焦小檔，讓 AI（與人）改某一塊時不必載入整檔。**行為完全不變**，正確性由既有 400 個測試背書。

## 策略決定

採 **方案 A：套件 + `__init__` 再匯出（facade）**。

理由：churn 最小、`app.py` 零改動、測試只動必要處。權衡過的替代方案：
- 方案 B（扁平 `chat_*.py` 兄弟檔＋明確匯入）：位置最直白，但要改 `app.py` 8 處匯入＋大量測試 import，churn 最大。
- 方案 C（套件但 `__init__` 留空）：仍需改 `app.py` 與測試匯入。

分兩階段、同一條 `dev` 分支、兩次 SDD、最後一次 merge 到 `main`（純 sentinel、不觸發線上部署）。階段 1（`chat.py`）先做、驗收全綠後才做階段 2（`app.py`）。

## 現況公開面（拆檔不可打破）

- `web/app.py` 以 `from .. import ... chat as chatmod ...` 使用：`stream_with_tools`、`format_pipeline_summary`、`build_system_prompt`、`build_messages`、`StreamFilter`、`parse_suggestions`、`apply_update`、`maybe_compact`、`maybe_curate_memory`、`build_export_md`。
- 測試以 `from career_sentinel import chat` 存取 `chat.X`，包含公開函式與會被 **monkeypatch** 的私有函式：`_execute_search`、`_execute_fetch_url`、`_execute_job_detail`、`_execute_tool`、`_pipeline_tool_json`、`_html_to_text`，以及常數 `TOOL_LOOP_MAX`、`COMPACT_KEEP`、`_JD_DESC_MAX`、`_FETCH_URL_MAX` 與 `chat.llm`。

## 階段 1：`chat.py` → `chat/` 套件

`chat.py` 改為 `chat/` 目錄，拆成 6 個聚焦子模組：

| 新檔 | 職責 | 搬入的符號 |
|---|---|---|
| `chat/prompt.py` | 系統提示與訊息組裝 | `format_pipeline_summary`、`_PIPE_GROUP_LIMIT`、`_PIPE_STATE_ORDER`、`_PIPE_STATE_LABEL`、`_CONTRACT`、`build_system_prompt`、`build_messages`、`_RESUME_MAX_CHARS` |
| `chat/suggestions.py` | `<suggestions>` 解析／串流過濾／套用 | `SUGGESTIONS_OPEN`、`SUGGESTIONS_CLOSE`、`_partial_marker_len`、`StreamFilter`、`parse_suggestions`、`ApplyResult`、`_as_str_list`、`apply_update` |
| `chat/memory.py` | 對話壓縮與記憶整理 | `COMPACT_THRESHOLD`、`COMPACT_KEEP`、`CURATE_THRESHOLD`、`maybe_compact`、`CuratedFacts`、`maybe_curate_memory` |
| `chat/export.py` | 匯出求職檔案 MD | `build_export_md` |
| `chat/tools.py` | 工具定義與執行 | `TOOLS`、`JOBS_RESULT_LIMIT`、`_execute_search`、`_FETCH_URL_MAX`、`_SCRIPT_STYLE_RE`／`_TAG_RE`／`_WS_RE`／`_MULTINL_RE`、`_html_to_text`、`_execute_fetch_url`、`_JD_DESC_MAX`、`_execute_job_detail`、`_pipeline_tool_json`、`_execute_tool` |
| `chat/orchestrator.py` | tool-use 串流迴圈 | `TOOL_LOOP_MAX`、`stream_with_tools` |

### 跨子模組相依（皆淺、無循環）

- `orchestrator` → `tools`（`_execute_tool`）、`llm`、`config.foundry_settings`
- `memory` → `store`、`llm`、`models`
- `suggestions` → `store`、`models`
- `prompt` → `models`、pipeline 型別
- `tools` → `scraper.search`、`jobfetch`、`pipeline`、`store`
- `export` → `store`、`models`

### `chat/__init__.py`

再匯出上表所有目前以 `chat.X` 被存取的名稱（公開與被測試觸及的私有皆含），並 `from .. import llm` 使 `chat.llm` 照舊。匯入子模組後，`chat.tools`、`chat.orchestrator` 等亦可作為套件屬性存取。

### 匯入端衝擊

- `web/app.py`：**完全不動**（`chatmod.X` 全數由 `__init__` 再匯出）。
- 測試：只需把對工具函式的 monkeypatch 目標由 `chat` 改為真正定義處 `chat.tools`（patch 必須打在函式實際所在模組才生效）。受影響的是這幾個測試函式：
  - `test_stream_with_tools_happy_path`、`test_stream_with_tools_loop_limit`、`test_stream_with_tools_error_no_jobs_event`（patch `_execute_search` → `chat.tools`）
  - `test_execute_tool_search_dispatch`、`test_execute_tool_search_dispatch_passes_page`（patch `_execute_search` → `chat.tools`）
  - `test_execute_tool_get_job_detail_dispatch`（patch `_execute_job_detail` → `chat.tools`）
  - `test_execute_tool_fetch_url_dispatch`（patch `_execute_fetch_url` → `chat.tools`）
  - 其餘（直接呼叫 `chat.X`、或 patch `creq_mod`/`jobfetch` 等外部模組者）**一字不改**。

## 階段 2：`web/app.py` → `web/routers/` 套件

依領域拆成多個 `APIRouter`：

- `routers/dashboard.py`：`snapshot`、`scrape`、`status`、`usage`（get/reset）、`schedule`（get/ack）
- `routers/settings.py`：`settings`（get/put）、`preferences`（get/put）
- `routers/resume.py`：`resume`（upload/diagnose/import104/get）
- `routers/jobs.py`：`match`、`tailor`、`apply/open`、`negotiate`、`search`、`recommend`、`research`
- `routers/chat.py`：`chat`（send/apply/get/clear）、`export`
- `routers/interviews.py`：`interviews`（dismiss/restore/PUT interviews）

共用相依（`_conn`／`store`／`runner`／`scheduler`／`_snapshot_payload`／request models）收斂到 `web/deps.py`；`create_app` 只負責建立共用狀態並掛載各 router。

**細部拆法（router 的相依注入方式）在階段 1 驗收後、撰寫階段 2 實作計畫時定案**，因為需依實際 closure 用法選 FastAPI 依賴注入或 `app.state`。本設計先鎖定領域切分與 `deps.py` 收斂方向。

## 測試策略

- 每個 SDD task 後跑 `./.venv/Scripts/python.exe -m pytest -q`，全程維持 400 綠。
- 純內部搬移，不新增行為測試；重構正確性由既有測試背書。
- 前端不動。

## 交付順序

階段 1 SDD 全綠 → 階段 2 SDD 全綠 → 一次 merge 到 `main`。

## 非目標（YAGNI）

- 不改任何執行期行為、API 形狀、回應格式。
- 不動前端。
- 不新增功能、不順手改寫無關程式。
- 不拆 `store.py`（402 行但單一職責、內聚）與 `models.py`（純 Pydantic model 集中）。
