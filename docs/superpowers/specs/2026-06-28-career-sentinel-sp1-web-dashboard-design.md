# 設計規格：career-sentinel SP1 — 本地 Web 殼 + 儀表板

- 日期：2026-06-28
- 範圍：`sentinel/`；career-sentinel 從 CLI 長出本地 web app，呈現 `run` 的資料 + 網頁觸發抓取
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)（SP1，整體第一個 web 子專案）

## 背景與目標

career-sentinel（Phase 1+2 完成）目前是 CLI：`career-sentinel run` 爬 104 三類資料、存 SQLite、
比對、LLM 彙整、印在終端機。使用者想要一個**本地 web 介面**作為後續所有功能（設定/關注清單、
履歷健檢、JD 比對、推薦、排程通知）的地基。

SP1 是這個 web app 的**地基 + 第一個畫面**：一個本地 FastAPI 伺服器 + React 儀表板，
把現有 `run` 的三類資料與彙整搬上網頁，並提供網頁上的「重新抓取」按鈕觸發實際爬取。
**全地端、單人**——碰私人 104 資料，不上雲。

成功定義：`career-sentinel serve` 起本地伺服器、開瀏覽器，看到三類資料 + 今日彙整；
按「重新抓取」會實際爬一次 104（headful）、爬完畫面更新。

### 非目標（Out of scope，留後續 SP）

- 設定/關注清單（SP2）、履歷健檢（SP3）、JD 比對（SP4）、推薦（SP5）、排程通知（SP6）。
- SSE 即時進度條（重新抓取先用背景執行緒 + 輪詢；即時進度留待需要時補）。
- 多人/認證（地端單人，伺服器只綁 localhost）。
- 不改 Phase 1/2 既有的 store/diff/digest/scraper/browser 行為（只新增 web 層與一個共用的抓取 runner）。

## 技術選型（已與使用者確認）

| 層 | 選擇 |
|----|------|
| 後端 | FastAPI + uvicorn（Python，貼合 career-sentinel） |
| 前端 | React 18 + Vite + Mantine 7 + TanStack Query + TypeScript |
| 樣式 | **從雲端 app 複製** theme/全域樣式到 `sentinel/web/frontend/`（保持地端自包、不跨 import `frontend/`） |
| 抓取觸發 | 背景執行緒（headful Playwright）+ 前端輪詢 `/api/status`（SSE 留後續） |
| 伺服 | dev 用 vite（proxy 到 FastAPI）；正式 `npm run build` → FastAPI 服務 `dist/` |

## 架構

```
career-sentinel serve  → uvicorn 起 FastAPI（綁 127.0.0.1）+ 自動開瀏覽器
   FastAPI:
     GET  /api/snapshot  → 最新快照(三類)+diff+彙整+上次更新+failed_readers
     POST /api/scrape    → 背景執行緒跑一次抓取（重用 run 管線）；回 {status}
     GET  /api/status    → {running, last_run, last_error?}
     GET  /*             → 服務 React 靜態檔（dist/）
   背景抓取 runner（web/scraper_runner.py）：包 real.establish_session+scrape+存+管線，
     單例（同時只一個）、記錄 running/last_run/last_error
   前端（React）：三面板 + 彙整 + 重新抓取鈕 + 輪詢
```

新增模組，**不改既有**：

| 檔案 | 職責 |
|------|------|
| `sentinel/src/career_sentinel/web/__init__.py` | web 子套件 |
| `sentinel/src/career_sentinel/web/runner.py` | 背景抓取 runner（單例狀態 + 跑管線）；可單測（注入假 scrape） |
| `sentinel/src/career_sentinel/web/app.py` | FastAPI app + 三個 API + 靜態檔服務；`create_app()` 工廠 |
| `sentinel/src/career_sentinel/cli.py`（改） | 加 `serve` 子命令（起 uvicorn + 開瀏覽器） |
| `sentinel/web/frontend/` | React+Vite+Mantine 前端（自己的 package.json） |

## 資料 / API 合約

### `GET /api/snapshot`
讀 store 最新快照、算跟上次的 diff、產生彙整文字。回：
```json
{
  "run_at": "2026-06-28T19:10:00" | null,
  "viewers": [{ "company": "...", "job_title": "...", "viewed_at": "..." }],
  "applications": [{ "job_id": "...", "company": "...", "title": "...", "status": "...", "applied_at": "..." }],
  "messages": [{ "thread_id": "...", "company": "...", "last_message": "...", "has_interview_invite": true }],
  "digest": "今日彙整文字…",
  "failed_readers": []
}
```
- 無任何快照時：各清單空、`run_at: null`、`digest: "尚無資料，請先重新抓取"`。
- `failed_readers` 取最近一次抓取記錄（runner 保存；無則空）。

### `POST /api/scrape`
- 若已在跑 → 回 HTTP 409 `{ "status": "already_running" }`。
- 否則啟動背景執行緒跑一次抓取（headful），立即回 `{ "status": "running" }`。

### `GET /api/status`
```json
{ "running": false, "last_run": "2026-06-28T19:10:00" | null, "last_error": null | "請先 career-sentinel login" }
```

## 背景抓取 runner（`web/runner.py`）

單例狀態物件（模組級）持有 `running: bool`、`last_run: str|None`、`last_error: str|None`、
`last_failed_readers: set[str]`。

- `start_scrape(launch_scrape) -> bool`：若 `running` 回 False（拒絕）；否則設 `running=True`、
  起一個 `threading.Thread` 跑 `launch_scrape()`，結束時設 `running=False`、更新 `last_run`/`last_error`。
- `launch_scrape` 預設實作（`_default_scrape`）：開 playwright context → `real.establish_session(page)`；
  未登入 → `last_error="請先 career-sentinel login"`、不存；否則 `real.scrape(page)` → 用既有
  `run_pipeline` 的存+沿用邏輯存進 store，記 `last_failed_readers`。
- 可注入 `launch_scrape` 以單測（不開瀏覽器）：測「拒絕並行」、「狀態轉換」、「例外設 last_error」。

> 抓取 runner 與 `cli._cmd_run` 共用同一條「establish→scrape→pipeline 存」邏輯。實作時把該段
> 抽成一個可重用函式（如 `scraper.real.scrape_and_store(page, conn)` 或 runner 內部），cli 與 web 都呼叫，避免重複。

## 前端儀表板

- **三面板**：誰看過我 / 我的應徵 / 訊息·面試（各列清單；訊息標出面試邀約）。
- **今日彙整**區（顯示 `digest`）。
- **頂部**：「上次更新 <run_at>」+「重新抓取」按鈕。`failed_readers` 非空時顯示 ⚠️ 提示。
- **互動**：按鈕 → `POST /api/scrape`（409 則提示「已在抓取中」）→ 每 2s 輪詢 `/api/status`，
  `running` 期間鈕顯示 loading；轉 idle 後 refetch `/api/snapshot` 重繪；`last_error` 非空則顯示該錯誤。
- 用 TanStack Query 管 snapshot 查詢與 status 輪詢。
- 視覺沿用雲端 Cockpit 風（複製 theme/`.jt-*` 樣式）。

## 錯誤處理

- 未登入/session 過期：runner 設 `last_error`，`/api/status` 帶出，前端顯示「請先 career-sentinel login」。
- 單一讀取器失敗：沿用既有 `failed_readers` 容錯（沿用上次快照），`/api/snapshot` 帶出、前端標 ⚠️。
- 並行抓取：`/api/scrape` 回 409。
- 後端只綁 `127.0.0.1`（不對外）。

## 測試

- **後端 API**（FastAPI `TestClient` + 暫時 SQLite、不開瀏覽器）：
  - `/api/snapshot`：先用 store 存一筆快照 → 端點回對應三類 + digest；無快照 → 空 + 提示。
  - `/api/scrape`：注入假 `launch_scrape`（不開瀏覽器）→ 回 `running`；並行第二次 → 409。
  - `/api/status`：抓取中/完成/失敗三態。
- **runner**：注入假 scrape 測「拒絕並行」「例外→last_error」「成功→last_run 更新」。
- **真實 headful 抓取**：一次手動 `serve` + 按「重新抓取」驗證（同 Phase 2，不單測）。
- **前端**：沿用雲端慣例——`npm run build` 通過為閘門 + 人工目視；無 FE 單元測試。
- Phase 1/2 既有測試不得回歸。

## 開放問題（實作時釐清，不阻擋設計）

- `serve` 是否每次自動 `npm run build`，或要求使用者先 build——傾向：若 `dist/` 不存在則提示先 build，dev 用 vite。
- Playwright sync API 在 FastAPI（async）下需跑在獨立執行緒——runner 用 `threading.Thread` 已隔離；確認不卡事件迴圈。

## 後續

SP1 完成後接 SP2（設定+關注清單）等，見路線圖。即時進度（SSE）、通知會在後續 SP 補。
