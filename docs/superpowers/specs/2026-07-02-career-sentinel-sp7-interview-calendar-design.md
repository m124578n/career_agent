# 設計規格：career-sentinel SP7 — 面試擷取 + 加入 Google 日曆

- 日期：2026-07-02
- 範圍：`sentinel/`；擷取 104 面試邀約（公司/職缺/日期/地點）→ 儀表板列「即將到來的面試」→ 每筆預填 Google 日曆連結
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)（SP7）

## 背景與目標

career-sentinel 已有：讀 104 登入後資料（Phase 2：viewers/applications/messages）、web 儀表板（SP1）、
設定+關注（SP2）、履歷健檢（SP3）、JD 比對（SP4）、工作推薦（SP5）、站內搜尋（SP-Search）、
定期提醒+桌面通知（SP6）。

原始願景之一是「面試自動進行事曆、不錯過面試」。SP7 補上這塊——擷取結構化面試場次
（公司/職缺/確切日期時間/地點/狀態），在儀表板顯眼列出「即將到來的面試」，每筆提供一顆
「加入 Google 日曆」預填連結（點一下開 Google Calendar 新增事件頁、日期標題已填好）。

**行事曆整合方式（使用者選定）**：**預填 Google Calendar 連結**（`calendar.google.com/calendar/render?action=TEMPLATE&...`）
——零 OAuth、零 API，貼合地端瀏覽器已登入 Google 的現實。非完整 Calendar API 自動建事件。

成功定義：在儀表板「即將到來的面試」區塊看到面試場次（公司/職缺/日期/地點），點「加入 Google 日曆」
開啟預填好日期與標題的 Google Calendar 新增事件頁。

### 非目標（Out of scope，留後續）

- Google Calendar API 自動建事件（用預填連結，不碰 OAuth）。
- 面試進 diff / 進 SP6「N 筆新動態」通知（新面試邀約已由既有 message `has_interview_invite` → `new_invites` 粗略涵蓋；SP7 不重複做通知）。
- 全分頁 / 歷史面試 / 面試提醒排程。

## 技術選型

| 項目 | 選擇 |
|------|------|
| 面試擷取 | 新 reader `scraper/interviews.py`，**併入既有 scrape session**（headful 登入態，與 viewers/applications/messages 同 `page.request.get` 模式） |
| 行事曆 | **預填 Google Calendar 連結**（純函式產 URL，零外部整合） |
| 持久化 | 併入既有 Snapshot（面試為第 4 類資料，存快照） |
| 前端 | 儀表板加「即將到來的面試」區塊 |

## 後端模組

| 檔案 | 職責 | 對外介面 |
|------|------|---------|
| `scraper/interviews.py`（新） | 面試場次讀取器 | `INTERVIEWS_URL: str`、`parse_interviews(payload: dict) -> list[Interview]`（純函式、可單測）、`fetch_interviews(page) -> list[Interview]`（登入態；需真瀏覽器、不單測） |
| `calendar_link.py`（新，純函式） | Google 日曆預填連結 | `build_gcal_link(iv: Interview) -> str` |
| `models.py`（改） | 型別 | `Interview(company, job_title, when, location, status, thread_url, raw)`；`Snapshot` 加 `interviews: list[Interview]` |
| `scraper/real.py`（改） | 併入 reader | `scrape` 的 readers 加 `("interviews", fetch_interviews)`；`Snapshot` 帶 interviews |
| `cli.py`（改） | carry_forward | `_carry_forward` 加 interviews 第 4 欄位（既有技術債：目前寫死三欄位） |
| `web/app.py`（改） | 快照輸出 | `_snapshot_payload` 加 interviews |

- `Interview.when`：確切日期時間字串（抓到時）；抓不到時為空/None（fallback）。`thread_url`：對話室連結（供 fallback「開對話室查看」）。
- `parse_interviews`：容錯——欄位缺失/型別非預期時該筆略過或給預設，不整批炸。實際欄位路徑 writing-plans 抓真實 payload 確認。
- `build_gcal_link`：`https://calendar.google.com/calendar/render?action=TEMPLATE&text=<面試：公司>&dates=<起>/<迄>&details=<職缺>&location=<地點>`，全參數 URL-encode；`when` 為空時**不帶 `dates`**（讓使用者自己填時間）。日期格式 Google 要求 `YYYYMMDDTHHMMSS`（或帶 Z 的 UTC）——writing-plans 依真實 `when` 格式定轉換，預設面試時長 1 小時（起→起+1h）。

## API

- 不新增端點。面試併入既有 `GET /api/snapshot` 的輸出（`_snapshot_payload` 加 `interviews` 陣列，每筆含 `company/job_title/when/location/status/thread_url/gcal_link`）。
- `gcal_link` 由後端以 `build_gcal_link` 產生後放進 payload（前端直接用）。
- 擷取沿用既有 `POST /api/scrape`（併入 reader）。

## 前端

- 儀表板（`Dashboard.tsx`，改）：頂部（面試有時效性、顯眼）加「**即將到來的面試**」區塊。
  - 每筆面試卡：公司／職缺／**日期時間**（`when`，無則顯示「日期未擷取」）／地點／狀態 badge。
  - 每筆「**加入 Google 日曆**」外連（`gcal_link`，`target=_blank`）。
  - fallback：`when` 為空 → 顯示「開對話室查看」連結（`thread_url`）+ 不預填日期的日曆連結。
  - 排序：按 `when`，最近在前（無日期者排後）。
  - 無面試 → 不顯示該區塊。
- `api.ts`：`SnapshotResp` 加 `interviews: Interview[]`；`Interview` 介面。

## 錯誤處理

- `interviews` reader 失敗 → 併入既有 scrape reader 容錯（單一失敗記進 `failed_readers`、沿用上次、不中斷其他）。
- **既有技術債處理**：`cli._carry_forward` 目前寫死 viewers/applications/messages；加 interviews 第 4 欄位（否則 interviews 失敗時漏沿用）。
- `parse_interviews` 對壞資料容錯（略過壞筆），不因單筆異常炸整批。
- 後端只綁 127.0.0.1；面試資料只在本地。

## 測試

- `parse_interviews`：去識別化 fixture → 正確欄位（公司/職缺/日期/地點/狀態）；壞筆略過。
- `build_gcal_link`：有 `when` → 正確 URL（`dates=起/迄`、text/location/details URL-encode、預設 1h 時長）；無 `when` → 不帶 `dates` 的 fallback 連結。
- `_carry_forward` 加 interviews：`failed` 含 `interviews` 時沿用上次同類。
- `_snapshot_payload` 含 interviews + gcal_link。
- `fetch_interviews`（需登入態）不單測——真機驗證（有面試邀約時看清單 + 點日曆連結）。
- 前端 `npm run build` + 目視。
- 既有 142 測試不得回歸。

## 開放問題（writing-plans 探，不阻擋設計）

- 面試專屬端點 URL 與回應結構：`work/message/ajax/options` 的 `optionsMessageInterviewList`（FINDINGS 線索）是否含結構化面試場次？還是需開對話室（`chatrooms` 的某端點）取確切日期？writing-plans 用登入 profile 抓真實 payload 確認、做去識別化 fixture。
- 確切日期時間的欄位名與格式（時間戳/字串/時區）——決定 `build_gcal_link` 的日期轉換。
- 面試狀態值（coming/pending/attended/absent/canceled）的中文對應。
- 若列表端點無確切時間 → 確認 fallback（顯示面試但不預填日期）足夠，或評估開對話室成本（每場一次請求）。

## 後續

SP7 完成後，「不錯過面試」閉環成形。後續見路線圖（SP8 對話式、SP9 公司評價、站內搜尋進階篩選）。
