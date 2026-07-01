# 設計規格：career-sentinel SP5 — 工作推薦（逐筆手動比對）

- 日期：2026-07-01
- 範圍：`sentinel/`；拉出 104 個人化推薦職缺清單、標出命中關注、每筆可單獨比對吻合度
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)（SP5）

## 背景與目標

career-sentinel 已有：讀登入後資料的爬蟲（Phase 2）、設定/關注清單（SP2，`watch.is_watched`）、
履歷健檢（SP3）、JD × 履歷比對引擎（SP4，`jobfetch` + `match` + `POST /api/match`）。

使用者想要「定期檢視符合條件的職缺、看與自己履歷的吻合度」。SP5 聚焦**推薦清單 + 逐筆手動比對**：
拉出使用者 104 的個人化推薦職缺，標出命中關注公司/關鍵字的，每筆提供一個「比對」按鈕，
按下才對該筆抓 JD + 打 LLM 算吻合度（**重用 SP4，完全不改 `POST /api/match`**）。

**比對粒度決策**：逐筆手動比對（使用者選定）。每筆比對 = 一次 curl_cffi 抓 JD + 一次 LLM 呼叫（約 20 秒、會計費），
故不做「一鍵批次比對全部」——避免一次拉一整頁就打十幾次 LLM。

成功定義：在 web「推薦」分頁按「拉取推薦」，看到推薦職缺清單（職稱/公司/薪資 + 命中關注的 ★關注 標記）；
對任一列按「比對」，看到該職缺的吻合度分數（0~100）+ 契合理由 + 缺少技能。

### 非目標（Out of scope，留後續 SP）

- 一鍵批次比對 / 依吻合度分數排序（SP6）。
- 推薦結果持久化（本 SP **stateless**——每次拉取即時取得最新，不存 DB；比對結果也不存）。
- 全分頁抓完整推薦（本 SP 先抓第 1 頁；全分頁列入技術債）。
- 定期自動拉取 + 通知（SP6）。

## 技術選型

| 項目 | 選擇 |
|------|------|
| 推薦拉取 | 重用爬蟲的登入 session 模式：headful rebrowser（過 Cloudflare + 讀登入態）→ `page.request.get` 推薦端點 |
| 命中關注 | 重用 SP2 的 `watch.is_watched(title, company, settings)`（純函式） |
| 比對 | 重用 SP4 的 `POST /api/match`（貼 `job_url` → 抓 JD → LLM 比對），前端傳該筆推薦的 url |
| 持久化 | 無（stateless，重新拉取即更新） |
| 前端 | 接既有 Tabs（儀表板/履歷健檢/JD 比對），新增第四分頁「推薦」 |

## 後端模組

| 檔案 | 職責 | 對外介面 |
|------|------|---------|
| `scraper/recommend.py`（新） | 推薦解析 + 登入態讀取器（**parse 與 fetch 同檔，比照既有 `scraper/viewers.py`/`applications.py`/`messages.py`**） | `RECOMMEND_URL: str`、`parse_recommendations(payload: dict) -> list[RecommendedJob]`（純函式、可單測）、`fetch_recommendations(page) -> list[RecommendedJob]`（`page.request.get` + `parse_recommendations`；需真瀏覽器、不單測）、`recommend_session() -> list[RecommendedJob] \| None`（開 headful context → `establish_session` → `fetch_recommendations`；未登入回 `None`；需真瀏覽器、不單測） |
| `models.py`（改） | 型別 | `RecommendedJob(code: str, url: str, title: str, company: str, salary: str = "", is_watched: bool = False)` |
| `web/app.py`（改） | API | `GET /api/recommend` |

- `recommend_session()`：鏡像既有 `scraper/real.py` 的 `scrape_session()`——
  `sync_playwright` → `browser.open_context(p)` → `establish_session(page)`（未登入回 `None`）→ `fetch_recommendations(page)` → `finally: ctx.close()`。
- `fetch_recommendations(page)`：`page.request.get(RECOMMEND_URL)` 取 JSON → `parse_recommendations` → list。
- `parse_recommendations(payload)`：純函式，容錯——欄位缺失/型別非預期時該筆略過或給預設，不整批炸掉（跑真實多樣資料要穩）。
- `RecommendedJob.is_watched` 預設 `False`；由 API 層用 settings 算後填入（純函式 `parse_recommendations` 不碰 settings/DB）。

## API（接 `web/app.py`）

- `GET /api/recommend`（sync `def` → FastAPI 走 threadpool，headful 阻塞 ~15s 不擋事件迴圈）：
  - `recommend_session()` 回 `None`（未登入）→ **409**「請先在終端機執行 `career-sentinel login`」。
  - `recommend_session()` raise（抓取/解析失敗）→ **502**「拉取推薦失敗，請重試」。
  - 成功 → 讀 `resolved_db` 的 settings，對每筆算 `watch.is_watched(title, company, settings)` 填 `is_watched` → 回 `{"jobs": [RecommendedJob...]}`。
  - 空清單（登入但無推薦）→ 200 `{"jobs": []}`（前端顯示「目前沒有推薦」）。
- 用 `create_app` 的 `resolved_db` 讀 settings（與其他端點同 DB）。stateless（不存推薦）。
- 比對沿用既有 `POST /api/match`（不改）。

## 前端

- `App.tsx` 的 Tabs 加第四分頁「**推薦**」（`RecommendPage`），value `"recommend"`。
- `RecommendPage`：
  - 「拉取推薦」按鈕 → `GET /api/recommend`（loading ~15s，提示「正在開啟瀏覽器拉取…」）。
  - 未登入（409）→ 顯示後端 `detail`（提示終端機 login）；其他錯誤顯示 `detail`。
  - 清單每列：**職稱／公司／薪資** + 命中關注顯示 `★關注` badge + 「**比對**」按鈕 + 「去 104 看」外連（`url`，`target=_blank`）。
  - 履歷未上傳（`GET /api/resume` 的 `has_resume` 為 false）→ 比對按鈕禁用 + 提示「請先到『履歷健檢』上傳履歷」。
  - 按「比對」→ `POST /api/match {job_url: row.url}` → 該列展開/顯示 **吻合度分數**（0~100，數字 + Progress）+ **契合理由**（✓ 清單）+ **缺少技能**（! 清單）。比對中該列 loading；失敗顯示後端 `detail`。逐列各自獨立比對狀態。
  - 用 TanStack Query 管 `["recommend"]`（拉取）與 `["resume"]`（判 has_resume）；比對用一次性 POST（非 query），結果存 component state per row。

## 順手強健化（SP4 review minors，逐筆比對多樣職缺仍受益）

- `jobfetch.parse_job_detail`：specialty 逐項加 `isinstance(s, dict)` 保護 + 濾掉空字串（推薦來的職缺多樣，結構更容易有例外）。
- `models.MatchResult.score` 或 `match.match`：把分數 clamp 到 0~100（避免 LLM 回 120 撐破前端 Progress，或回非整數/超界導致 500）。採 clamp（夾住）而非 reject（免因 LLM 略微超界就 500）。

## 錯誤處理

- 各錯誤 → 對應 HTTP 碼與訊息（見 API）。前端統一顯示後端 `detail`。
- 後端只綁 127.0.0.1；登入態與個人資料只在本機；推薦不存 DB。
- `parse_recommendations` 對壞資料容錯（略過壞筆），不因單筆結構異常炸掉整批。

## 測試

- **`parse_recommendations`**：對真實擷取的去識別化 fixture → 正確欄位（code/url/title/company/salary）；壞筆（缺欄位/型別異常）→ 略過不炸。
- **`is_watched` 整合**：settings 有關注公司/關鍵字 → 對應推薦筆 `is_watched=True`，未命中 `False`。
- **API**（TestClient + 暫時 SQLite）：monkeypatch `scraper.recommend.recommend_session` 回假清單 → 200 且含 `is_watched`；回 `None` → 409；raise → 502。
- **強健化**：`parse_job_detail` 對 specialty 含非 dict / 空字串 → 不炸、濾除；`match`/`MatchResult` 分數超界（如 120、-5）→ clamp 到 0~100。
- **`fetch_recommendations`/`recommend_session`**：需真瀏覽器 + 真登入態，不單測——真機步驟：`career-sentinel serve` → 推薦分頁 → 拉取 → 看清單 → 對一筆按比對看分數。
- **前端**：`npm run build` 通過 + 人工目視（拉取、看 ★關注、按比對看分數/理由/缺口）。
- Phase 1/2/SP1/SP2/SP3/SP4 既有 102 測試不得回歸。

## 開放問題（實作時釐清，不阻擋設計）

- 推薦端點確切 URL / host（`https://www.104.com.tw/api/jobs/personal-recommend-jobs`？query 參數 page/pageSize/order 等）與回應 JSON 結構——寫計畫時用 career-sentinel 的登入 profile 抓一筆真實 payload 確認、做成去識別化 fixture。
- 該端點是否需 `www.104.com.tw` host 的 Cloudflare clearance（`establish_session` 目前 navigate `pda.104.com.tw`）——真機驗證；若 www host 需獨立 clearance，`recommend_session` 改先 navigate 一個 www 頁再打端點。
- 職缺 `code` → 詳情 `url` 的組法（`https://www.104.com.tw/job/{code}`，與 SP4 `extract_job_code` 對稱）——抓 payload 時確認 code 欄位來源。

## 後續

SP5 完成後接 SP6（定期檢視 + 通知排程：按設定時間自動跑爬取/推薦/比對、命中關注即通知；會重用本 SP 的推薦拉取與 SP4 的比對）。見路線圖。
