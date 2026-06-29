# 設計規格：career-sentinel SP4 — JD × 履歷比對

- 日期：2026-06-30
- 範圍：`sentinel/`；貼 104 職缺網址 → 抓完整 JD → 對已存履歷算吻合度 + 缺少技能
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)（SP4）

## 背景與目標

career-sentinel 已有履歷健檢（SP3）與 provider-aware `llm.parse_json`（OpenAI 相容 + Azure Foundry）。
使用者想要「根據某職缺的 JD 與自己的履歷，列出缺少的技能與吻合度」。

雲端 career_agent 已有 `services/job_matching.py`（`analyze(target, job, detail) -> MatchAnalysis{score,reasons,gaps,benefits}`）
與 `crawler` 的 `fetch_job_detail`（curl_cffi 打 104 公開詳情 API）。SP4 把這兩塊**移植到地端**並接上 web。

本 SP 聚焦**比對引擎 + 抓單一 JD**：貼一個 104 職缺網址，抓完整 JD，對 SP3 已上傳的履歷算吻合度與缺口。
「自動拉一批推薦職缺多選比對」是 SP5（會重用本 SP 的比對引擎與 JD 抓取）。

成功定義：在 web「JD 比對」分頁貼一個 104 職缺網址、按比對，看到該職缺的標題/公司 +
吻合度分數（0~100）+ 契合理由 + 缺少技能。

### 非目標（Out of scope，留後續 SP）

- 批次/推薦多選比對、排序（SP5）。
- 比對結果持久化（本 SP **stateless**，不存）。
- 福利標籤（雲端 MatchAnalysis 有 benefits；本 SP MVP 先不做，留 SP5/後續）。

## 技術選型

| 項目 | 選擇 |
|------|------|
| JD 抓取 | **curl_cffi**（Chrome TLS 指紋，過 104 TLS fingerprinting；雲端同款）打公開詳情 API `https://www.104.com.tw/job/ajax/content/{code}` |
| 結構化 LLM | 重用 SP3 的 `llm.parse_json`（provider-aware，支援 Foundry） |
| 持久化 | 無（stateless 比對） |
| 前端 | 接 SP1/SP3 的 Tabs，新增「JD 比對」分頁 |

## 後端模組

| 檔案 | 職責 | 對外介面 |
|------|------|---------|
| `jobfetch.py` | 104 公開 JD 抓取 | `extract_job_code(url: str) -> str`、`parse_job_detail(payload: dict) -> JobDetail`（純）、`fetch_job_detail(code: str, *, session=None) -> JobDetail`（curl_cffi；需真網路、不單測） |
| `match.py` | 比對引擎 | `build_prompt(resume_text, target_title, jd: JobDetail) -> str`、`match(resume_text, target_title, jd, *, client=None) -> MatchResult` |
| `models.py`（改） | 型別 | `JobDetail(title, company, salary, location, description, work_exp, education, majors, specialties)`、`MatchResult(score: int, reasons: list[str], gaps: list[str])` |

- `extract_job_code`：104 職缺網址形如 `https://www.104.com.tw/job/{code}`（可能帶 query/結尾斜線）→ 取 `/job/` 後的末段 code；非 104 職缺網址 raise `ValueError`。
- `parse_job_detail`（移植雲端，欄位路徑寫計畫時以真實 payload 確認）：`data.jobDetail`（jobDescription/salary/addressRegion）+ `data.condition`（workExp/edu/major/specialty[].description）+ header 的職稱/公司。
- `fetch_job_detail`：`curl_cffi` Session(impersonate="chrome")，帶 `Referer: https://www.104.com.tw/job/{code}`，GET 詳情 API → `parse_job_detail`。
- `match`：`build_prompt`（移植雲端：目標職位/薪資/履歷/JD description/work_exp/education/specialties → 評吻合度 0~100 + 理由 + 缺口）→ `llm.parse_json(prompt, MatchResult, system=<求職顧問>)`。

## API（接 `web/app.py`）

- `POST /api/match`（body `{job_url: str}`）：
  - `extract_job_code` 失敗（非 104 職缺網址）→ 400「請貼 104 職缺網址」。
  - `fetch_job_detail` 失敗（網路/104 擋/壞 code）→ 502「抓取職缺失敗，請確認網址」。
  - 已存履歷 `resume_text` 為空 → 400「請先上傳履歷」。
  - 無 LLM key（`llm.parse_json` raise `RuntimeError`）→ 400「請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY」。
  - LLM 失敗 → 500「比對失敗，請重試」。
  - 成功 → 回 `{title, company, salary, score, reasons, gaps}`。
- 用 `create_app` 的 `resolved_db` 載履歷（與其他端點同 DB）。stateless（不存）。

## 前端

- Tabs 加第三個分頁「**JD 比對**」（`MatchPage`）。
- `MatchPage`：
  - 職缺網址 TextInput（placeholder 範例 104 網址）+「比對」按鈕。
  - 履歷未上傳 → 提示「請先到『履歷健檢』上傳履歷」（`GET /api/resume` 的 `has_resume`）。
  - 比對中 loading；失敗顯示後端 `detail`。
  - 結果：職缺**標題/公司/薪資** + **吻合度分數**（0~100，數字 + 簡單能量條/Progress）+ **契合理由**（✓ 清單）+ **缺少技能**（! 清單）。
- 用 TanStack Query 共用 `["resume"]`（判斷 has_resume）；比對用一次性 POST（非 query）。

## 錯誤處理

- 各錯誤 → 對應 HTTP 碼與訊息（見 API）。前端統一顯示後端 `detail`。
- 後端只綁 127.0.0.1；履歷文字只在本地。

## 測試

- **`extract_job_code`**：標準網址、帶 query、結尾斜線 → 正確 code；非 104 網址 → `ValueError`。
- **`parse_job_detail`**：對真實擷取的去識別化 fixture → 正確欄位（description/work_exp/specialties/title/company）。
- **`match`**：`build_prompt` 含目標/履歷/JD；`match` 用假 client（monkeypatch `llm.llm_provider`→openai）→ `MatchResult`。
- **API**（TestClient + 暫時 SQLite）：monkeypatch `jobfetch.fetch_job_detail`（回假 JobDetail）+ `match.match`（回假 MatchResult）→ 200；非 104 網址→400；無履歷→400。
- **`fetch_job_detail`/curl_cffi**：需真網路、不單測——真機步驟用真實 104 職缺網址驗證。
- **前端**：`npm run build` 通過 + 人工目視（貼真網址、看分數/理由/缺口）。
- Phase 1/2/SP1/SP2/SP3 既有測試不得回歸。

## 開放問題（實作時釐清，不阻擋設計）

- 104 詳情 payload 的 header 職稱/公司確切路徑——寫計畫時抓一筆真實 payload 確認、做成 fixture。
- 104 詳情 API 是否需 warmup（雲端有 `_warmup`）——真機驗證時確認；不行就加 warmup。

## 後續

SP4 完成後接 SP5（工作推薦：拉 104 推薦清單 + 過濾 + 重用本 SP 的 `match` 批次比對排序）。見路線圖。
