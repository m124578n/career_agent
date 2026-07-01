# 設計規格：career-sentinel SP-Search — 站內關鍵字職缺搜尋 + 比對

- 日期：2026-07-01
- 範圍：`sentinel/`；輸入關鍵字 → 站內爬 104 職缺搜尋結果 → 列出 → 逐筆對履歷比對
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)

## 背景與目標

career-sentinel 願景是**一站式求職中心**。目前已有：讀 104 登入後資料（Phase 2）、web 儀表板（SP1）、
設定+關注（SP2）、履歷健檢（SP3）、JD×履歷比對（SP4）、個人化工作推薦（SP5）。

推薦（SP5）是**被動**的——104 依 profile 塞給你。缺的是**主動搜尋**：使用者想用自己的關鍵字找工作。
本 SP 補上這塊——站內用關鍵字爬 104 職缺搜尋結果、列出、直接對履歷比對，讓「找工作 → 評估吻合度」
全在 career-sentinel 站內完成，不必跳回 104 官網。

成功定義：在 web「職缺搜尋」分頁輸入關鍵字（預設帶入設定的關注關鍵字）、按搜尋，看到 104 職缺結果清單
（職稱/公司/薪資），對任一筆按「比對」看到吻合度分數 + 契合理由 + 缺少技能。

### 非目標（Out of scope，留後續）

- 進階篩選（地區/薪資/經歷/產業等 104 篩選條件）——本 SP 只吃關鍵字。
- 全分頁（本 SP 先抓第 1 頁；全分頁列技術債）。
- 搜尋結果持久化（stateless，不存 DB）。
- 把搜尋納入定期排程/通知（SP6 排程只管職動態）。

## 技術選型

| 項目 | 選擇 |
|------|------|
| 搜尋抓取 | **押注 `curl_cffi`**（Chrome TLS 指紋，像 SP4 抓 JD）直打 104 公開職缺搜尋 API——104 搜尋是公開資料、不需登入，故輕量、不彈 Chrome、不撞瀏覽器鎖。**若真端點需登入態則 fallback headful**（像 SP5），writing-plans 時探真端點確認。 |
| 結構化解析 | **重用 SP5 `parse_recommendations` 的欄位映射**（搜尋結果職缺結構與推薦幾乎相同） |
| 型別 | **重用 SP5 `RecommendedJob`**（code/url/title/company/salary/is_watched），不新增型別 |
| 比對 | **重用 SP4 `POST /api/match`**（逐筆手動，與 SP5 一致） |
| 持久化 | 無（stateless） |
| 前端 | 新「職缺搜尋」分頁，**重用 SP5 推薦分頁的逐列比對元件** |

## 後端模組

| 檔案 | 職責 | 對外介面 |
|------|------|---------|
| `scraper/search.py`（新） | 關鍵字搜尋 104 職缺 | `SEARCH_URL: str`、`parse_search(payload: dict) -> list[RecommendedJob]`（純函式、可單測；重用推薦欄位映射）、`fetch_search(keyword: str, *, session=None) -> list[RecommendedJob]`（curl_cffi；需真網路、不單測） |
| `web/app.py`（改） | API | `GET /api/search?kw=...` |

- `parse_search`：與 `parse_recommendations` 同樣的職缺欄位映射（jobNo→code、jobName→title、custName→company、link.job→url、salary 編碼）；壞筆略過不炸。實際 payload 欄位路徑 writing-plans 時抓真實 payload 確認（可能與推薦略有差異）。
- `fetch_search`：`curl_cffi` Session(impersonate="chrome")，帶適當 Referer，GET 搜尋 API（帶 keyword query）→ `parse_search`。是否需 warmup 真機驗證。

## API（接 `web/app.py`）

- `GET /api/search?kw=<keyword>`：
  - `kw` 為空/空白 → 400「請輸入搜尋關鍵字」。
  - `fetch_search` 失敗（網路/104 擋）→ 502「搜尋失敗，請重試」。
  - 成功 → 讀 settings 對每筆算 `watch.is_watched(company, title, settings)` 填 is_watched → 回 `{"jobs": [RecommendedJob...]}`。
  - 空結果（搜到但無職缺）→ 200 `{"jobs": []}`。
- 用 `create_app` 的 `resolved_db` 讀 settings（與其他端點同 DB）。stateless（不存）。
- 比對沿用既有 `POST /api/match`（不改）。

## 前端

- `App.tsx` 的 Tabs 加分頁「**職缺搜尋**」（`SearchPage`）。
- 先把 SP5 推薦分頁的逐列比對卡片抽成共用元件（若尚未抽）：`JobRow`（收 `job: RecommendedJob` + `canMatch`），供推薦與搜尋共用。
- `SearchPage`：
  - 搜尋 TextInput，預設帶入 `settings.watched_keywords` 合成字串（空白分隔），可即時改；「搜尋」按鈕（或 Enter 觸發）。
  - 履歷未上傳（`GET /api/resume` 的 `has_resume` false）→ 比對鈕禁用 + 提示（同 SP5）。
  - 搜尋中 loading；空結果顯示「找不到符合的職缺」；失敗顯示後端 detail。
  - 結果清單：每筆用共用 `JobRow`（職稱/公司/薪資 + ★關注 + 去 104 看外連 + 逐列「比對」→ 展開 吻合度/理由/缺口）。
- `api.ts`：加 `searchJobs(kw: string)`（`GET /api/search?kw=`，回 Response 或解析後清單，與既有 getter 風格擇一並保持一致）。

## 錯誤處理

- 各錯誤 → 對應 HTTP 碼與訊息（見 API）。前端統一顯示後端 detail。
- 後端只綁 127.0.0.1；搜尋結果只在本地、不存。
- `parse_search` 對壞資料容錯（略過壞筆），不因單筆結構異常炸整批。

## 測試

- **`parse_search`**：對去識別化 fixture → 正確欄位（code/url/title/company/salary）；壞筆略過。
- **`is_watched` 整合**：settings 有關注公司/關鍵字 → 對應搜尋結果筆 is_watched=True。
- **API**（TestClient + 暫時 SQLite）：monkeypatch `search.fetch_search` 回假清單 → 200 且含 is_watched；空 kw → 400；fetch 拋 → 502。
- **`fetch_search`/curl_cffi**：需真網路、不單測——真機用真關鍵字（如「Python」）驗證。
- **前端**：`npm run build` 通過 + 人工目視（搜關鍵字、看結果、按比對看分數）。
- 既有測試（Phase 1/2/SP1–SP5，及 SP6 若已併入）不得回歸。

## 開放問題（writing-plans 時釐清，不阻擋設計）

- **104 搜尋端點確切 URL 與是否需登入**：writing-plans 時用 curl_cffi 直打候選端點（如 `www.104.com.tw/jobs/search/api/jobs?keyword=...` 或 `/jobs/search/list`）抓真實 payload；確認 (1) 是否公開（curl_cffi 可打）、(2) keyword query 參數名、(3) 回應 JSON 結構與職缺欄位路徑（對照推薦 payload 差異）、(4) 是否需 warmup/Referer。若公開不可行則改 headful（像 SP5 recommend），並據此調整計畫。
- **搜尋結果職缺欄位是否與推薦完全相同**：抓 payload 時確認，若有差異則 `parse_search` 獨立映射而非直接呼叫 `parse_recommendations`。

## 後續

本 SP 完成後，「找工作 → 比對」站內閉環成形。後續可接：進階篩選、SP6 定期提醒（plan 已就緒待執行）、
SP7 行事曆、SP8 對話式、SP9 公司評價。見路線圖。
