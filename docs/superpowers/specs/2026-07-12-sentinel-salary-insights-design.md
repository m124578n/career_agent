# career-sentinel 薪資行情分析 — 設計

**日期**：2026-07-12
**範圍**：`sentinel/` 子專案；新增功能（RecommendedJob 結構化薪資 + 聚合模組 + API + 聊天唯讀工具 + UI 面板）。

## 目標

對一個關鍵字（職稱），把 104 搜尋結果的薪資聚合成月薪中位數與區間（p25–p75），回報樣本數與面議比例，作為「期望薪資」的參考與 offer 議價的市場依據。純用 104 搜尋資料、快且免費，不接外部薪資站。

## 動機與資料現況

`RecommendedJob.salary` 目前是格式化字串（「月薪 60,000~90,000 元」「年薪 1,200,000 元以上」「面議」），原始數字（`salaryLow`/`salaryHigh`/期間碼 `s10`）在 `scraper/recommend.py:_format_salary` 就被丟棄。搜尋（`scraper/search.py`）也走 `parse_recommendations`，故在解析時保留結構化薪資即可讓搜尋結果攜帶可聚合的數字，避免回頭硬解字串。

## 使用者決定（已確認）

- **資料來源**：在解析時保留結構化薪資欄位（非回頭解析字串）。
- **換算**：統一月薪；月薪照舊、年薪÷12；**時薪與面議排除**（各自計數回報）。
- **入口**：聊天唯讀工具 `salary_insights` + UI 面板（找職缺頁），兩者皆有。

## 架構

### ① 資料層：`RecommendedJob` 結構化薪資

- `RecommendedJob`（`models.py`）加三欄（皆有預設、向後相容）：
  ```python
  salary_low: int = 0       # 原始下限（依 period 單位）
  salary_high: int = 0      # 原始上限；「以上」開放式或面議為 0
  salary_period: str = ""   # "月薪" / "年薪" / "時薪"；面議為 ""
  ```
- `scraper/recommend.py`：抽出 `_salary_fields(job) -> tuple[int, int, str]`（回 low, high, period）；`salary_low`/`high`/`period` 填入。規則：`s10==10` 或 low、high 皆 0 → 面議（0, 0, ""）；`high >= 9999999`（「以上」）→ high 存 0；period 由 `_PERIOD`（40 時薪 / 50 月薪 / 60 年薪）對應。`_format_salary` 保留產生 UI 用的字串（可改為呼叫 `_salary_fields` 再格式化，避免重複邏輯）。
- `parse_recommendations` 建 `RecommendedJob` 時帶入這三欄。搜尋（`parse_search` 委派本函式）自動獲得。

### ② 聚合層：`salary_insights.py`（新檔，純數學可單測）

- Model（放 `models.py`）：
  ```python
  class SalaryInsight(BaseModel):
      keyword: str = ""
      sample: int = 0            # 納入統計的職缺數（月/年薪且有數字）
      negotiable: int = 0        # 面議數
      hourly_excluded: int = 0   # 時薪排除數
      median_monthly: int | None = None
      p25_monthly: int | None = None
      p75_monthly: int | None = None
      min_monthly: int | None = None
      max_monthly: int | None = None
  ```
- `compute_salary_insights(keyword: str, jobs: list[RecommendedJob]) -> SalaryInsight`：
  - 逐筆分類：`salary_period == "時薪"` → `hourly_excluded += 1`、跳過；`salary_period not in ("月薪","年薪")` 或 `salary_low <= 0` → `negotiable += 1`、跳過。
  - 換算月薪：`ml = salary_low if 月薪 else round(salary_low/12)`；`mh = round(salary_high/12) if (年薪 and high>0) else (high if (月薪 and high>0) else 0)`；代表值 `rep = round((ml+mh)/2) if mh>0 else ml`。收集 `rep`（>0）。
  - 有樣本：`median_monthly`=中位數、`p25`/`p75`=第 25/75 百分位、`min`/`max`=代表值極值（皆 int）；`sample`=收集數。無樣本：統計欄皆 None、sample 0。
  - 百分位用簡單線性插值（見實作）；壞資料不炸。
- `salary_insights_for_keyword(keyword: str, *, pages: int = 3, session=None) -> SalaryInsight`：以 `fetch_search(keyword, page=p)` 抓 `pages` 頁、依 `code` 去重、丟給 `compute_salary_insights`。真網路、不單測（網路那層薄）。

### ③ API

- `GET /api/salary-insights?kw=&pages=3`（掛 `web/routers/jobs.py`）：`kw` 空 → 400；`pages` clamp 1–5；`salary_insights_for_keyword` 例外 → 502；回 `SalaryInsight.model_dump()`。唯讀、不需登入。

### ④ 聊天唯讀工具 `salary_insights`

- `chat/tools.py`：`TOOLS` 加一項 `salary_insights`（input `{keyword}`）；`_execute_tool` 分派 → `salary_insights_for_keyword(keyword, pages=3)` → 回精簡 JSON 文字（median/p25/p75/sample/negotiable）給 LLM，`(None, text, is_error)`（無前端事件，agent 自行織進回答）。失敗回 `(None, "查詢薪資行情失敗…", True)`。
- 為自動執行的唯讀工具（同 `search_jobs`/`get_pipeline`，僅 foundry tool-use 迴圈有）。`chat/prompt.py` 系統提示工具段補一句「salary_insights 查某職稱的 104 薪資行情（談薪資/offer 時可用）」。

### ⑤ 前端 UI 面板（找職缺頁）

- `api.ts`：`SalaryInsight` 型別 + `getSalaryInsights(kw): Promise<Response>`。
- `SalaryInsightPanel.tsx`（新）：關鍵字 `TextInput` + 查詢按鈕 → 顯示中位月薪（大字）、p25–p75 區間、min–max、樣本數 +「N 筆面議、M 筆時薪排除」；一顆「設為期望月薪」按鈕把 `median_monthly` 寫回偏好（`getPreferences` → 改 `expected_salary` → `putPreferences`，並 invalidate `["preferences"]`）。載入/錯誤/空樣本（顯示「這關鍵字多為面議，抓不到數字」）狀態齊全。
- 掛在 `FindJobsPage.tsx` 上方或側邊一個區塊。純 CSS/Mantine、不加圖表套件。

## 資料流

UI：`SalaryInsightPanel` → `GET /api/salary-insights?kw` → jobs router → `salary_insights_for_keyword`（抓 3 頁搜尋）→ `compute_salary_insights` → `SalaryInsight` → 面板顯示；「設為期望月薪」→ `putPreferences`。
聊天：agent 於 tool-use 迴圈呼叫 `salary_insights` 工具 → 同 `salary_insights_for_keyword` → JSON 文字回 LLM。

## 錯誤處理

- `kw` 空 → 400；抓取/網路失敗 → 502（API）或工具回 is_error；面議居多導致 sample 0 → 正常回（統計欄 None），前端/agent 說明資料稀少。
- 薪資解析壞值（非數字）以預設 0 處理、跳過該筆，不炸整批。

## 測試

- `tests/test_salary_insights.py`：`compute_salary_insights` — 月薪/年薪換算正確、時薪與面議分別排除且計數、中位與 p25/p75、空樣本回 None/0。
- `tests/test_scraper_recommend.py`（或既有搜尋/推薦解析測試）增補：`parse_recommendations` 對月薪區間、年薪、「以上」、面議四種 payload 正確填 `salary_low`/`salary_high`/`salary_period`。
- `tests/test_web_salary.py`：端點 monkeypatch `fetch_search` → 200 + 聚合 shape；`kw` 空 → 400。
- `tests/test_chat_tools.py`：`_execute_tool("salary_insights", {"keyword": …})` monkeypatch `salary_insights_for_keyword` → 回文字；系統提示提及 `salary_insights`。
- 前端 `npm run build`。

## 非目標（YAGNI）

- 不接外部薪資站（比薪水/Glassdoor）——那是 negotiate 的 web search。
- 不做歷史趨勢、地區/年資細分、薪資分佈圖。
- 不改既有 search/recommend 既有輸出（只加欄位）、不改 negotiate。
