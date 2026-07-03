# career-sentinel SP9：公司評價 web 研究 設計

> 日期：2026-07-03。狀態：使用者已核可設計，待 spike＋plan。
> 前情：SP1–SP8＋SP-UIUX＋驗收回饋輪完成、202 測試綠。

## 目標

在儀表板／推薦／搜尋看到公司名的地方**一鍵查公司評價**：用 LLM 自帶的 web search
上網搜「{公司名} 評價／面試／薪資 台灣」，彙整成結構化報告（風險燈號＋優缺點＋
薪資/面試觀察＋來源連結），彈窗顯示、SQLite 快取 7 天。

## 關鍵決策（使用者選定）

- **查詢管道＝LLM 自帶 web search**（非本機爬搜尋引擎、非直抓評價站）。
- **觸發點＝公司名旁一鍵查＋彈窗**（不做獨立分頁）。

## Spike 先行（實作 Task 0，過不了就停）

用使用者真實 key 驗證 provider 的 web search 能力：
- OpenAI 相容端點（`LLM_*`）：試 `model + ":online"` 後綴與 `plugins: [{"id": "web"}]`
  （OpenRouter 慣例）。
- Foundry（`FOUNDRY_*`）：試 Anthropic `web_search` server tool
  （`tools=[{"type": "web_search_20250305", "name": "web_search"}]`，實際 type 版本以
  anthropic SDK 當前版本文件為準，spike 時確認）。
- 產出：記錄哪個 provider 路徑可用、回應含來源與否、單次呼叫耗時與費用感。
- **兩者皆不支援 → 停止 SP9 回報使用者**，再議「本機搜尋＋抓頁餵 LLM」fallback，不硬做。

## 後端

### `research.py`（新模組）
- `research_company(name: str, *, client=None) -> CompanyResearch`：
  組 prompt（指示：以 web search 查「{name} 評價 面試 薪資 台灣」等關鍵字、
  優先台灣站點（面試趣/比薪水/Dcard/PTT/Google 評論）、只輸出單一 JSON 物件、
  沒查到資料的欄位留空並在 summary 說明資料稀少）→ provider-aware 呼叫
  （依 `config.llm_provider()` 分派，pattern 同 `llm.py`）→ `llm._extract_json`
  韌性解析 → 驗進 `CompanyResearch`。
- timeout 放寬（web search 呼叫可能 20–60 秒）。

### 模型（`models.py`）
```python
class ResearchSource(BaseModel):
    title: str = ""
    url: str = ""

class CompanyResearch(BaseModel):
    company: str = ""
    summary: str = ""                 # 總評一段
    pros: list[str] = []
    cons: list[str] = []
    salary_notes: str = ""            # 薪資觀察
    interview_notes: str = ""         # 面試觀察
    risk_level: str = "mid"           # low | mid | high（validator 白名單、預設 mid）
    sources: list[ResearchSource] = []
    researched_at: str = ""           # ISO，寫入時蓋
```

### 快取（`store.py`）
- 新表 `company_research (company TEXT PRIMARY KEY, data TEXT NOT NULL)`
  （**非** id=1 單列——以公司名為 key 的多列 KV）。
- `load_research(conn, company) -> CompanyResearch | None`、`save_research(conn, r)`。
- TTL：`researched_at` 距今 **7 天**內回快取；過期或 `force` 重查後覆寫。
  `RESEARCH_TTL_DAYS = 7` 常數。

### 端點（`web/app.py`）
- `GET /api/research?company=<名>[&force=1]`：
  - `company` 空 → 400；無 LLM key → 400（同 SP3 pattern）。
  - 快取命中且未過期且非 force → 直接回（`cached: true`）。
  - 否則呼叫 `research_company`，成功存快取回傳（`cached: false`）；
    例外 → 502「查詢失敗，請重試」。
  - 回傳＝`CompanyResearch.model_dump()` ＋ `cached` 欄位。
- 同步呼叫（前端 loading 等待），不做背景工作佇列（YAGNI）。

## 前端

- 新 `ResearchButton.tsx`：小 ActionIcon（IconZoomQuestion 之類、`title="查公司評價"`）＋
  自帶 Modal 狀態。放置點：Dashboard 各清單列的公司名旁（CompanyLink 旁）、
  `JobRow` 公司名旁（推薦/搜尋共用）。
- Modal 內容（由上而下）：公司名＋風險燈號 Badge（low=teal「低風險」/mid=amber「中性」/
  high=danger「高風險」）→ 總評 → 優點/缺點雙欄清單 → 薪資觀察、面試觀察 →
  來源連結列表（target=_blank）→ 底部「查於 {researched_at}」＋「重新查詢」
  （force=1，subtle 按鈕）。
- 互動：未查過→按鈕點擊才查（icon loading／Modal skeleton）；快取命中秒開；
  網路呼叫 try/finally 解鎖；錯誤在 Modal 內顯示訊息＋重試。
- 空資料韌性：pros/cons 空就不渲染該欄、sources 空顯示「無來源」。

## 邊界與成本

- **PII**：送出的只有公司名（與既有 LLM 使用同級，不新增出口類型）。
- web search 呼叫較貴且慢 → 快取 7 天＋只有使用者主動點擊才查；
  **不做**抓取後自動全量預查。
- 不做（YAGNI）：多公司批次查、歷史版本比較、獨立分頁、評價站直抓。

## 測試

- `research.py`：假 client 餵含 JSON 的回應→解析驗證；壞 JSON→例外（端點 502）。
- store：`load/save_research` round-trip、未存在回 None、覆寫更新。
- TTL：過期判斷純函式（7 天邊界）、force 略過快取。
- 端點：無 company 400、無 key 400、快取命中 `cached:true`、force 重查、502。
- 前端：build 零 TS 錯誤。
- 真機：spike 驗證 provider ＋ 實查 2–3 家使用者面試中的公司看品質。
