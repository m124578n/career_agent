# 設計規格：career-sentinel SP6 — 定期檢視提醒 + 桌面通知

- 日期：2026-07-01
- 範圍：`sentinel/`；serve 開著時到設定時間提醒「該檢視求職動態」，桌面通知 + 儀表板橫幅，使用者一鍵拉取
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)（SP6）

## 背景與目標

career-sentinel 已有：讀 104 登入後資料的爬蟲（Phase 2）、web 儀表板（SP1）、設定+關注清單（SP2，
`Settings.notify_time` 已存 HH:MM 但尚未使用）、履歷健檢（SP3）、JD 比對（SP4）、工作推薦（SP5）。

使用者想要「按設定時間自動檢視符合條件的職缺、命中即通知」。**硬限制**：爬 104 需 headful Chrome
過 Cloudflare（會彈視窗、不能純背景 headless），故無人值守全自動爬取不可靠。

**決策（使用者選定）**：採「**到點提醒、一鍵執行**」——排程器只負責「什麼時候該提醒」，
到點發桌面通知 + 儀表板橫幅，爬取仍由使用者按一下觸發。通知管道用**瀏覽器桌面通知**
（Web Notification API，未授權時 fallback 橫幅）。一鍵「立即拉取」**只拉職動態**（既有 `/api/scrape`），
推薦分開（橫幅次連結跳推薦分頁，走 SP5 既有流程）——不破壞 SP5 的 recommend stateless。

成功定義：serve 開著、`notify_time` 設定後，到點時（1）跳桌面通知「該檢視求職動態了」+ 儀表板頂部橫幅；
（2）按橫幅「立即拉取」跑既有 scrape；（3）拉完若有新動態，跳第二則桌面通知「發現 N 筆新動態」。

### 非目標（Out of scope，留後續）

- 無人值守自動爬取（headful 限制，非本 SP 目標）。
- 多個提醒時段（本 SP 單一 `notify_time`）。
- Email / 手機推播 / 作業系統原生通知（本 SP 只做瀏覽器 Web Notification）。
- 把推薦拉取納入一鍵（推薦走既有分頁）。
- 排程狀態持久化（純記憶體，serve 生命週期內）。

## 技術選型

| 項目 | 選擇 |
|------|------|
| 排程觸發 | serve 內 **daemon 背景執行緒**，每 30s 醒來比對現在時刻 vs `notify_time`；只設「提醒旗標」不自己爬 |
| 排程狀態 | **純記憶體**（serve 生命週期內），`due: bool` + `last_prompted_date`；不寫 DB |
| 桌面通知 | **Web Notification API**（純前端，未授權 fallback 橫幅與分頁標記） |
| 一鍵拉取 | 重用既有 `POST /api/scrape`（背景 headful，走 runner 忙碌鎖） |
| 前端輪詢 | 擴充儀表板既有輪詢，加 `GET /api/schedule` |

## 後端模組

| 檔案 | 職責 | 對外介面 |
|------|------|---------|
| `web/scheduler.py`（新） | 到點判斷（純函式）+ 背景執行緒 + 記憶體狀態 | `should_prompt(now: datetime, notify_time: str \| None, last_prompted_date: str \| None) -> bool`（純）、`start(load_settings: Callable[[], Settings]) -> None`（起 daemon thread）、`state() -> dict`（回 `{due, notify_time, last_prompted_date}`）、`ack() -> None`（清 due） |
| `web/runner.py`（改） | scrape 完成後記錄本次新增計數 | `default_scrape` 回傳 `ChangeCounts`；`_state` 加 `last_change_counts`；`status()` 回傳它 |
| `models.py`（改） | 型別 | `ChangeCounts(new_viewers: int, status_changes: int, new_messages: int, new_invites: int)`，含 `total` property |
| `web/app.py`（改） | API | `GET /api/schedule`、`POST /api/schedule/ack`；serve 啟動時 `scheduler.start(...)` |

- `should_prompt`：到點（`now` 的 HH:MM >= notify_time 且今天尚未提醒）→ True；未到點 / 今天已提醒（`last_prompted_date == now.date()`）/ `notify_time` 為 None → False。**啟動當下已過點不補觸發**由「當天視為已提醒」語意涵蓋——見開放問題釐清。
- 背景執行緒：每 30s 呼叫 `should_prompt`；True 時設 `due=True`、`last_prompted_date=今天`。任何例外吞掉不崩（daemon，比照 runner）。
- `default_scrape`（改）：現有流程 `scrape_session → run_pipeline` 存 snapshot；改為回傳本次 diff 的 `ChangeCounts`（run_pipeline 內本就算 diff，取其新增計數）。runner `_run` 存進 `_state.last_change_counts`。

## API（接 `web/app.py`）

- `GET /api/schedule` → `{"due": bool, "notify_time": str | None, "last_prompted_date": str | None}`（讀 `scheduler.state()`）。
- `POST /api/schedule/ack` → 清 due（使用者已看到提醒或已按拉取）→ 回 `{"due": false}`。
- `GET /api/status`（既有，改）→ 額外回 `last_change_counts: {new_viewers, status_changes, new_messages, new_invites}`（無資料時全 0）。
- serve 建 app 時呼叫 `scheduler.start(lambda: store.load_settings(_conn()))` 起背景執行緒。
- 後端只綁 127.0.0.1；排程狀態純記憶體、不寫 DB。

## 前端

- `api.ts`：加 `getSchedule()`、`ackSchedule()`、`ScheduleState` 型別；`StatusResp` 加 `last_change_counts`。
- 通知模組 `notify.ts`（新）：`ensurePermission()`（首次請求 Notification 授權）、`notify(title, body)`（已授權才發，否則 no-op）。
- 儀表板（`Dashboard.tsx`，改）：
  - 掛載時 `ensurePermission()`。
  - 既有輪詢加 `GET /api/schedule`；`due` 由 false→true 的邊緣：發桌面通知「⏰ 該檢視求職動態了」+ 顯示頂部橫幅。
  - 頂部橫幅（due 為 true 時顯示）：主按鈕「立即拉取」→ 呼叫既有 startScrape + `ackSchedule()`；次連結「也拉推薦」→ 切到推薦分頁；關閉鈕 → `ackSchedule()`。
  - scrape 由 running→done 的邊緣：讀 `status.last_change_counts`，`total > 0` → 發桌面通知「🔔 發現 N 筆新動態」；為 0 不發桌面通知（避免打擾）。
- 未授權桌面通知 → `notify` no-op，僅橫幅與既有儀表板標記生效（不阻斷功能）。

## 錯誤處理

- 排程器背景執行緒任何例外吞掉不崩（daemon）。
- `notify_time` 為 null → 排程器空轉、永不 due。
- serve 啟動當下已過 `notify_time` → 不立即補觸發（見開放問題的啟動語意）。
- Web Notification 未授權 / 被拒 → 靜默 fallback 橫幅，不報錯。
- 一鍵拉取沿用既有 scrape 錯誤處理（runner 忙碌鎖、失敗記 `last_error`）。

## 測試

- **`should_prompt`**（純函式，核心）：到點且今天未提醒→True；未到點→False；今天已提醒→False；`notify_time=None`→False；啟動已過點（當天已標記提醒）→False；跨日重置→True。
- **`default_scrape` 回傳計數**：monkeypatch `scrape_session` + 造前後兩份 snapshot（新增 viewer/狀態變化/新訊息/新邀約）→ `ChangeCounts` 正確；無變化→全 0。
- **`ChangeCounts.total`**：各欄位加總正確。
- **API**（TestClient + 暫時 SQLite）：`GET /api/schedule` 回預設（due false）；`POST /api/schedule/ack` 後 due false；`GET /api/status` 含 `last_change_counts`。
- **背景執行緒 / Web Notification**：不單測（需時間流逝 / 瀏覽器授權）——真機步驟：設 `notify_time` 為近未來、等橫幅 + 桌面通知、按立即拉取看拉取完成通知。
- **前端**：`npm run build` 通過 + 人工目視。
- Phase 1/2/SP1–SP5 既有 115 測試不得回歸。

## 開放問題（實作時釐清，不阻擋設計）

- **啟動已過點的精確語意**：serve 在 `notify_time` 之後啟動當天，是否該提醒一次？設計採「不補觸發」（避免每次重啟就跳）。實作方式：`scheduler.start` 時把 `last_prompted_date` 設為今天**當且僅當**啟動時刻已過 `notify_time`——如此當天不再觸發、隔天正常。寫計畫時把這條件寫進 `start` 並補測。
- **`run_pipeline` 取新增計數的確切接點**：`default_scrape` 目前呼叫 `cli.run_pipeline`；寫計畫時確認 diff 在何處算出、如何回傳計數（可能讓 `run_pipeline` 或 `default_scrape` 取 `diff.diff_against_last` 的結果）。

## 後續

SP6 完成後接 SP7（行事曆整合：面試確切日期擷取 + 自動進 Google Calendar，需開對話室/面試端點）。見路線圖。
