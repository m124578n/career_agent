# 設計規格：career-sentinel SP3 — 履歷健檢

- 日期：2026-06-29
- 範圍：`sentinel/`；上傳履歷 PDF → 針對目標職位 LLM 分析優勢/待補強，web 呈現
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)（SP3）

## 背景與目標

career-sentinel 已有本地 web 儀表板（SP1）+ 設定/關注（SP2）。使用者想要「履歷健檢」：
上傳履歷，針對某目標職位（+薪資）得到「優勢／待補強」分析。

雲端 career_agent 已有這套邏輯（`backend/.../services/resume_diagnosis.py`：`diagnose(target) -> {strengths, gaps}`，
用結構化 LLM 輸出；`resume/__init__.py` 用 pypdf 解析 PDF）。SP3 把這套**移植到地端 career-sentinel**並接上 web。

career-sentinel 目前的 LLM 層（`digest.py`）只有純文字 chat completions，無結構化輸出；
SP3 補一個 `llm.parse_json`（要 JSON、驗進 Pydantic）小工具，供本 SP 與日後 SP4/SP5 重用。

成功定義：在 web「履歷健檢」頁上傳 PDF、填目標職稱（選填薪資）、按「執行健檢」，
看到 LLM 產出的優勢清單與待補強清單；重開頁面仍見上次結果。

### 非目標（Out of scope，留後續 SP）

- JD × 履歷比對（SP4，會重用本 SP 的 `llm.parse_json`）。
- docx/多種格式（本 SP 僅 PDF + txt）；多份履歷版本管理。
- 額度限制（雲端有，地端單人不需）。

## 技術選型

| 項目 | 選擇 |
|------|------|
| PDF 解析 | `pypdf`（新依賴；雲端同款）；`.txt` 直接 decode |
| 結構化 LLM | 新 `llm.parse_json`：OpenAI 相容 chat + `response_format=json_object` + 指示 → `json.loads` → Pydantic 驗證 |
| 儲存 | 單列 `resume` 表（JSON），同 SP2 settings 模式 |
| 前端 | 接 SP1 React/Mantine；頂部加 Mantine Tabs（儀表板 / 履歷健檢） |
| LLM key | 沿用 `config.llm_settings`（`LLM_API_KEY`）；診斷必須有 key |

## 後端模組

| 檔案 | 職責 | 對外介面 |
|------|------|---------|
| `resume.py` | 履歷檔→純文字 | `parse_resume(filename: str, data: bytes) -> str`（PDF/txt；不支援 raise `ValueError`） |
| `llm.py` | 結構化 LLM | `parse_json(prompt: str, model_cls, *, system: str \| None = None, client=None) -> model_cls`（無 key raise） |
| `diagnosis.py` | 履歷診斷 | `build_prompt(resume_text, target_title, expected_salary) -> str`、`diagnose(resume_text, target_title, expected_salary, *, client=None) -> ResumeDiagnosis`（`ResumeDiagnosis` 由 `models` 匯入） |
| `store.py`（改） | 履歷狀態持久化 | `load_resume(conn) -> ResumeState`、`save_resume(conn, state: ResumeState)` |
| `models.py`（改） | 型別 | `ResumeDiagnosis(strengths, gaps)` 與 `ResumeState(resume_text: str, target_title: str, expected_salary: int \| None, diagnosis: ResumeDiagnosis \| None)` **皆放 `models.py`**（避免 models↔diagnosis 循環匯入）；`diagnosis.py` 從 models 匯入 |

- `llm.parse_json`：組 messages（system 可選 + user prompt 含「只回 JSON，鍵為 …」）、POST `{base_url}/chat/completions`（帶 `response_format={"type":"json_object"}`）、取 `choices[0].message.content`、`json.loads` → `model_cls.model_validate(...)`。`client` 可注入測試。無 `api_key` → raise `RuntimeError("請先設定 LLM_API_KEY")`。
- `diagnose`：`build_prompt`（移植雲端：目標職位/期望月薪/履歷內容 + 指示分析優勢與待補強）→ `llm.parse_json(prompt, ResumeDiagnosis, system=<求職顧問>)`。

## 資料 / API（接 `web/app.py`）

`ResumeState` 以 JSON 存單列 `resume` 表（id=1）。

- `POST /api/resume/upload`（multipart `file`）→ `parse_resume` → 存 `resume_text`（保留既有 target/diagnosis）→ 回 `{"chars": <int>}`。解析失敗（不支援格式）→ 400。
- `POST /api/resume/diagnose`（body `{target_title: str, expected_salary: int | None}`）：
  - 已存 `resume_text` 為空 → 400「請先上傳履歷」。
  - 無 `LLM_API_KEY` → 400「請先設定 LLM_API_KEY」。
  - 否則 `diagnose(...)` → 存（resume_text + target + diagnosis）→ 回 `ResumeDiagnosis`。
- `GET /api/resume` → `{"has_resume": bool, "chars": int, "target_title": str, "expected_salary": int | None, "diagnosis": ResumeDiagnosis | None}`。

（`/api/resume/*` 用 `create_app` 的 `resolved_db`，與其他端點同 DB。）

## 前端

- 頂部加 **Mantine Tabs**：「儀表板」（現有 `Dashboard`）、「履歷健檢」（新 `ResumePage`）。重構 `main.tsx` 渲染一個含 Tabs 的 `App`。
- `ResumePage`：
  - 上傳 PDF：file input → `POST /api/resume/upload`（multipart）→ 顯示「已載入 N 字」。
  - 目標職稱（TextInput）+ 期望月薪（NumberInput，選填）。
  - 「執行健檢」按鈕 → `POST /api/resume/diagnose`（loading；錯誤顯示後端訊息如「請先設定 LLM_API_KEY」）→ 顯示**優勢（✓ 清單）**與**待補強（! 清單）**。
  - 開頁 `GET /api/resume` 還原 has_resume/target/上次 diagnosis。
- 用 TanStack Query 管 `/api/resume` 查詢。

## 錯誤處理

- 不支援格式 / 解析空白 → upload 400，前端顯示。
- 無履歷 → diagnose 400「請先上傳履歷」。
- 無 LLM key → diagnose 400「請先設定 LLM_API_KEY」。
- LLM 回非 JSON / 驗證失敗 → diagnose 500，前端顯示「健檢失敗，請重試」。
- 後端仍只綁 127.0.0.1；履歷文字只進本地 gitignore 的 `data/` DB。

## 測試

- **`parse_resume`**：`.txt` 解析、不支援副檔名 raise `ValueError`。（PDF 抽取由真機步驟用真實 PDF 驗證——pypdf 可信、不另造 fixture。）
- **`llm.parse_json`**：注入假 client 回 `{"strengths":[...],"gaps":[...]}` → 得 `ResumeDiagnosis`；無 key → raise。
- **`diagnosis`**：`build_prompt` 含目標職稱/履歷片段；`diagnose` 用假 client → 回 `ResumeDiagnosis`。
- **store**：`load/save_resume` round-trip（含 diagnosis）；無資料 → 預設空 `ResumeState`。
- **API**（TestClient + 暫時 SQLite）：upload 一個 `.txt` → chars；diagnose 在 monkeypatch `diagnosis.diagnose`（不打真 LLM）下回結果並存；無履歷 diagnose → 400；GET round-trip。
- **前端**：`npm run build` 通過 + 人工目視（上傳真實 PDF、執行健檢、看到優勢/缺口）。
- Phase 1/2/SP1/SP2 既有測試不得回歸。

## 開放問題（實作時釐清，不阻擋設計）

- `response_format=json_object` 若使用者的端點不支援 → 退回「prompt 要求 JSON + 容錯解析」；真機驗證時確認。

## 後續

SP3 完成後接 SP4（JD × 履歷比對，重用 `llm.parse_json`）。見路線圖。
