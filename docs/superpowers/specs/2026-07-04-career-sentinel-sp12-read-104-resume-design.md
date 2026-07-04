# career-sentinel SP12：讀 104 履歷 + 健檢 + 開編輯頁 設計

> 日期：2026-07-04。狀態：使用者已核可設計，待 plan。
> 前情：SP1–SP11b 完成、233 測試綠。**spike 已完成**（`spike/capture_resume.py`、發現記於 `spike/FINDINGS.md`）。

## Spike 結論（已驗證，本 SP 不再 spike）

104 線上履歷是**結構化**且**登入態 XHR 讀得到**：
- 主端點 `GET pda.104.com.tw/profile/ajax/resumeByBlock?vno=<vno>` → `{data, metadata}` 信封。
- 履歷清單取 `vno`：`GET pda.104.com.tw/profile/ajax/completeResumeList?top=isMaster`。
- 編輯頁：`pda.104.com.tw/profile/edit?vno=<vno>`。
- `data` 分區塊（各塊 `formData` 內）：info(基本資料/PII)、education、experience、
  jobCondition、skill、certificate、language、project、portfolio、bio(自傳)、referrer；
  另有 `progress`（完成度%）。
- **PII 警示**：info 區塊含姓名/email/手機/地址/生日/身分證——健檢送 LLM 前必須剝除。

## 範圍決策（使用者選定）

讀真實 104 履歷 → 針對它做健檢/改善建議 → 開編輯頁使用者親手改。
**寫入維持 SP11b 原則：agent 不寫入 104**（改履歷由使用者在編輯頁親手做）。

## 後端讀取（新 scraper）

### `scraper/resume104.py`
- `RESUME_LIST_URL = "https://pda.104.com.tw/profile/ajax/completeResumeList?top=isMaster"`
- `RESUME_BLOCK_URL = "https://pda.104.com.tw/profile/ajax/resumeByBlock?vno={vno}"`
- `parse_resume104(payload: dict) -> Resume104`（純函式、可單測）：從 `data` 解析各區塊成
  `Resume104Block(id, label, text, completed)`，`text` 是該區塊攤平的可讀文字。壞筆略過不炸。
- `fetch_resume104(page) -> Resume104`（需真瀏覽器、不單測）：
  1. `page.request.get(RESUME_LIST_URL)` → 取 master 履歷的 `vno`。
  2. `page.request.get(RESUME_BLOCK_URL.format(vno=vno))` → `parse_resume104`。
  resp 非 ok raise RuntimeError（同 interviews/recommend 慣例）。
- `resume104_session()`（同 `recommend.recommend_session` 的登入態 session 建立、pda host clearance）：
  開登入態 context → `fetch_resume104(page)`；未登入回 None。

### 區塊攤平（`parse_resume104` 內，欄位來自 spike 實測）
- **info**（基本資料，含 PII）：name/email/gender/birthYear/cellphone/city/street…（顯示用、標記 PII）。
- **experience** `experiences[]`：companyName/jobName/jobCat/duration/description/skill/management/industry。
- **education** `educations[]`：name(校)/departments/highest/duration/status。
- **skill** `skills[]`：name/desc/tag。
- **certificate**：certificates/others/certifications。
- **language** `languages`：foreign/local。
- **project** `projects[]`：name/duration/introduction/url。
- **bio** `bio`：chi(中文自傳)/eng。
- jobCondition/portfolio/referrer：不納入（求職條件/作品連結/他人資訊，健檢無用）。

### 模型（`models.py`）
```python
class Resume104Block(BaseModel):
    id: str          # info/experience/education/skill/certificate/language/project/bio
    label: str       # 顯示名（基本資料/工作經歷/…）
    text: str        # 攤平可讀文字
    is_pii: bool = False  # info=True，健檢時排除
    completed: bool = False

class Resume104(BaseModel):
    vno: str = ""
    progress: int = 0
    blocks: list[Resume104Block] = Field(default_factory=list)
```

### 端點（`web/app.py`）
- `GET /api/resume104`：on-demand、`try_begin_browser` 序列化（同 `/api/recommend`）：
  忙碌→409、未登入（session None）→409「尚未登入，請先 career-sentinel login」、失敗→502、
  成功→`Resume104.model_dump()`。**讀取結果留本地顯示、不外送。**
- `POST /api/resume104/diagnose` body `{target_title, resume104}`（前端把讀到的 blocks 傳回）：
  攤平**非 PII 區塊**（`is_pii=False` 的 blocks 的 text 串接）→ 重用
  `diagnosis.diagnose(flat_text, target_title, None)` → 回 `ResumeDiagnosis`。
  無 key→400、生成失敗→500。**PII 區塊（info）不進 LLM。**
  - 抽 helper `flatten_for_diagnosis(r: Resume104) -> str`（純函式、可單測：驗 PII 區塊不出現）。

## 前端——新分頁「104 履歷」（第八 Tab）

- `Sidebar` 加導覽項（IconId 系）、`App` 加 `page === "resume104"`。
- `Resume104Page.tsx`：
  - 「讀取我的 104 履歷」按鈕（會開瀏覽器抓、loading）→ 顯示各區塊（`Paper`／`whiteSpace: pre-wrap`，
    含基本資料——只是把你自己的資料顯示回給你、留本地）。
  - 「健檢」按鈕（讀到才啟用）→ `POST /api/resume104/diagnose`（帶 target_title——沿用 resume state 的 target_title
    或頁內輸入）→ 顯示優勢（teal）/待補強（amber），重用健檢視覺。
  - 「開啟編輯頁」按鈕 → **重用 SP11b `/api/apply/open`**（傳 `profile/edit?vno=<vno>`——它本是開任意 http(s) URL；
    vno 從讀取結果取）→ 登入態 Chrome 開編輯頁、你親手改存。
  - 網路呼叫 try/finally；409/502 頁內 danger 顯示；不持久化。
- `api.ts`：`Resume104`/`Resume104Block` 介面、`getResume104()`、`diagnoseResume104(target_title, resume104)`。

## 邊界與安全

- agent **不寫入 104**（改履歷由使用者在編輯頁親手做，同 SP11b）。
- 讀取 read-only、on-demand、瀏覽器序列化（`try_begin_browser`）；殺 Chrome 只殺本專案 profile。
- **PII 邊界**：讀取結果顯示在本地 UI（你自己的資料、不外送）；健檢送 LLM 前剝除 info(PII) 區塊。
- 不做（YAGNI）：本地 vs 104 diff、自動寫回、多份履歷管理、逐區塊編輯、快取。

## 測試

- `parse_resume104`：假 resumeByBlock payload（仿 spike 結構）→ 驗各區塊解析、vno、progress、
  info 標 is_pii、壞筆略過。
- `flatten_for_diagnosis`：驗 info(PII) 區塊文字**不出現**、內容區塊（experience/education/skill/bio）**有**。
- 端點：`/api/resume104`（monkeypatch session：忙碌 409/None 409/例外 502/成功結構）、
  `/api/resume104/diagnose`（PII 剝除 + 重用 diagnosis、無 key 400）。
- 前端 build 零 TS 錯誤。
- 真機：讀 104 履歷→顯示各區塊→健檢→開編輯頁（登入態 Chrome 開 profile/edit）。
