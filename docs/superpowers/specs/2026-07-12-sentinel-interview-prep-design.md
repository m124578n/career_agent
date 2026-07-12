# career-sentinel 面試準備助手 — 設計

**日期**：2026-07-12
**範圍**：`sentinel/` 子專案；新增功能（LLM 任務 + tracked 欄位 + API + 職缺卡按鈕 + 聊天 run-card）。

## 目標

面試前，依職缺 JD、使用者履歷與比對缺口，生成一份面試準備：可能考題、針對缺口的追問防雷、要主動帶出的亮點、面試前複習清單；可選「深度模式」再上網搜這間公司的面試心得。結果存在該職缺上，隨時可回看。面試後的心得記錄沿用既有的面試紀錄（`interview_note`），不重做。

## 動機

現有面試相關功能只有「事後記錄」（JobCardDrawer 面試紀錄 + agent 的 interview_note 卡）。本功能補上「事前準備」，與比對缺口（`MatchResult.gaps`）、JD、履歷高度綜效，並沿用既有 LLM 任務的模式（同 tailor/negotiate：模組 + 回傳 model + API + run-card/按鈕）。

## 使用者決定（已確認）

- **資料來源**：預設快版（JD + 履歷 + 缺口，`llm.parse_json`）；可選「深度模式」加 `research.web_search_complete` 搜公司面試心得、附來源。
- **持久化**：存在 tracked job（新 `interview_prep_json` 欄），可回看、可重新產生。
- **入口**：職缺卡（JobCardDrawer）按鈕 + 聊天 agent run-card 兩者皆有。

## 架構

沿用既有 LLM 任務三段式（模組 / 資料 / API+前端），與 `negotiate.py`+`NegotiateButton.tsx`+`NegotiateCard` 對稱。

### ① LLM 任務 `interview_prep.py`（新檔）

- `build_interview_prep_prompt(jd: JobDetail, resume_text: str, gaps: list[str], target_title: str, *, deep: bool) -> str`
  - 帶入 JD（職稱/公司/需求/JD 內文）、履歷全文（截斷）、既有比對缺口（有才帶；沒有則指示 LLM 自行從 JD 與履歷推斷缺口）、目標職稱。
  - 指示只輸出單一 JSON（無 markdown 圍欄），欄位對應 `InterviewPrep`。
  - `deep=True` 時追加指示：用網路搜尋這間公司「{company}」在台灣的面試心得/考古題（可參考 Dcard、PTT Tech_Job、Glassdoor、面試趣），把常見題型與流程納入；`sources` 只列實際參考網頁。`deep=False` 時不談 sources。
- `prepare_interview(jd, resume_text, gaps, target_title, *, deep=False, client=None, feature="面試準備") -> InterviewPrep`
  - `deep=False`：`llm.parse_json(prompt, InterviewPrep, feature=feature, client=client)`。
  - `deep=True`：`text = research.web_search_complete(prompt, feature=feature, client=client)`；`InterviewPrep.model_validate(json.loads(llm._extract_json(text)))`。
  - 設 `r.deep = deep`、`r.prepared_at = datetime.now().isoformat(timespec="seconds")`，回傳。

### ② 資料 model 與 store

- 新 model（`models.py`）：
  ```python
  class InterviewPrep(BaseModel):
      likely_questions: list[str] = []      # 可能考題
      gap_watchouts: list[str] = []         # 缺口可能被追問 + 建議回法
      talking_points: list[str] = []        # 你的亮點，主動帶出
      prep_checklist: list[str] = []        # 面試前複習清單
      sources: list[ResearchSource] = []    # 深度模式才有
      deep: bool = False
      prepared_at: str = ""
  ```
- `TrackedJob` 加欄位 `interview_prep_json: str = ""`（放在 `interviews_json` 之後）。
- `store.py`：
  - `_SCHEMA` 的 `tracked_jobs` 加 `interview_prep_json TEXT NOT NULL DEFAULT ''`。
  - `_migrate` 的欄位補齊迴圈把 `"interview_prep_json"` 併入（ALTER TABLE 冪等）。
  - `load_tracked_jobs` / `get_tracked_job` / `upsert_tracked_job` 的 SELECT/INSERT 欄位加 `interview_prep_json`。
  - `set_interview_prep(conn, code, prep: InterviewPrep) -> None`（整筆存、保留其他欄位、`updated_at=now`；不存在則建列）。
  - **關鍵（carry-forward，與 `interviews_json`/`offer_json` 同類雷）**：`merge_tracked_job` 既有分支加 `new_ip = existing.interview_prep_json`（else `""`）並在 upsert 帶入；`set_tracked_state` 既有分支的 upsert 加 `interview_prep_json=existing.interview_prep_json`。否則下次擷取或改狀態會清空面試準備。

### ③ API（tracked router）

- 於 `web/routers/tracked.py` 新增：
  ```python
  class _InterviewPrepReq(BaseModel):
      deep: bool = False

  @router.post("/api/tracked/{code}/interview-prep")
  def interview_prep_ep(code, req, db_path=Depends(get_db_path)):
      # 需履歷；抓 JD；取既有 gaps；prepare；存檔；回 InterviewPrep
  ```
  - 流程：`code` 空 → 400；讀 resume，無內文 → 400「請先上傳履歷」；讀 tracked job 取 `url`（或以 code 組 104 網址）→ `jobfetch.fetch_job_detail(code)`，失敗 → 502；gaps 從 tracked 的 `match_json`（若有 `MatchResult`）取，否則 `[]`；`prefs.target_title`；呼叫 `interview_prep.prepare_interview(...)`（`RuntimeError` → 400、其他 → 500）；`store.set_interview_prep(conn, code, prep)`；回 `prep.model_dump()`。
- `GET /api/tracked/{code}`（同 router）回應加 `interview_prep`：`json.loads(tj.interview_prep_json) if tj.interview_prep_json else None`。

### ④ 前端

- `api.ts`：`InterviewPrep` 型別（對齊後端）＋`interviewPrep(code, deep): Promise<Response>`（POST）；`TrackedCard`（GET 回傳型別）加 `interview_prep: InterviewPrep | null`。
- `InterviewPrepView.tsx`（新）：渲染 `InterviewPrep`（分區：可能考題 / 缺口防雷 / 你的亮點 / 準備清單 / 來源），與 `NegotiationView` 同風格。
- **職缺卡按鈕**：`InterviewPrepButton`（可併入 `InterviewPrepView.tsx` 或 JobCardDrawer 內）：ActionIcon/Button + Modal，內含「深度模式」開關與「產生 / 重新產生」；載入態、錯誤重試（同 `NegotiateButton`）。掛在 JobCardDrawer 面試紀錄區旁。抽屜開啟時若 `interview_prep` 已存在則直接顯示、可重產。
- **聊天 run-card**：`chat.py` 的 `_CONTRACT` 加 `interview_prep`（op `run`，payload `{code, company, title}`）與規則（面試前想準備某職缺時提議；code 必來自 get_pipeline/search_jobs；只提議、按下才花錢）；系統提示工具段可提及。`ChatPage.tsx` 對 `s.field === "interview_prep"` 渲染 `InterviewPrepCard`（含深度開關、按鈕，按下呼叫 `interviewPrep`），與既有 `TailorCard`/`NegotiateCard` 對稱；`FIELD_LABEL` 加 `interview_prep: "面試準備"`。
  - 注意：`interview_prep` 是 **run-card**（前端直接呼叫端點），**不進** `apply_update` 的 `ALLOWED`（與 tailor/negotiate 一致）。

## 資料流

面試前：職缺卡按鈕 或 聊天 run-card → `POST /api/tracked/{code}/interview-prep {deep}` → tracked router → 抓 JD + 履歷 + gaps → `interview_prep.prepare_interview` →（深度走 web search）→ `set_interview_prep` 存檔 → 回 `InterviewPrep` → 前端 `InterviewPrepView` 顯示。回看：`GET /api/tracked/{code}` 帶出 `interview_prep`。

## 錯誤處理

- 無履歷 → 400「請先上傳履歷」；抓 JD 失敗 → 502；LLM `RuntimeError`（如無 key）→ 400；其他 → 500。前端顯示錯誤 + 重試。
- 深度模式較慢（20–60 秒），前端載入態註明。
- LLM 回傳非法 JSON → `prepare_interview` 內 `json.loads`/`model_validate` 例外向上拋，端點轉 500。

## 測試

- `tests/test_interview_prep.py`：
  - `build_interview_prep_prompt` 含 JD 職稱/公司、履歷片段、gaps；`deep=True` 含公司搜尋指示、`deep=False` 不含。
  - `prepare_interview`（fake client）：快版 → `llm.parse_json` 解析出 `InterviewPrep`、`deep=False`、`prepared_at` 有值；深度版 monkeypatch `research.web_search_complete` 回含 sources 的 JSON → `deep=True`、`sources` 非空。
- `tests/test_tracked_jobs_store.py` 增補：`set_interview_prep` 持久化；`merge_tracked_job`/`set_tracked_state` 沿用 `interview_prep_json`（回歸，仿既有 `interviews_json` 測試）。
- `tests/test_web_interview_prep.py`：端點 monkeypatch `jobfetch.fetch_job_detail` + `interview_prep.prepare_interview` → 200、回傳 shape、已存檔（再 GET 帶出 `interview_prep`）；無履歷 → 400。
- 前端 `npm run build`。

## 非目標（YAGNI）

- 不做「面試後寫心得」（沿用既有 `interview_note`）。
- 深度模式外不接其他外部服務。
- 不做自動/排程預先準備、不做多輪面試分階段準備。
- 不改既有 tailor/negotiate/match 行為。
