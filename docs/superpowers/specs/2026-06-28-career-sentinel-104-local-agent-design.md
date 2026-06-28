# 設計規格：104 地端哨兵（career-sentinel）MVP

- 日期：2026-06-28
- 範圍：**全新獨立地端 Python CLI 程式**（不屬於現有雲端 career_agent，獨立 repo / 資料夾）
- 狀態：設計已確認，待寫實作計畫
- 代號：`career-sentinel`（暫定，可改）

## 背景與目標

現有 career_agent 是「雲端、多人、平台出 key、使用者按按鈕同步觸發」的工具，
只取用 104 的**公開搜尋 API**，刻意不碰使用者帳密。

本案是一個野心更大的進階構想——一個**自主的 career agent**，每天替使用者整理
求職狀況。它與現有雲端版是**兩種不同的信任模型與部署模式**：

| | 現有 career_agent | 本案 career-sentinel |
|---|---|---|
| 部署 | 雲端、多人、平台出 key | **地端、單人、自帶 key** |
| 觸發 | 使用者按按鈕、同步即時 | 手動 `run`（未來每天自動跑） |
| 資料 | 公開 104 搜尋 API | **登入後的私人頁面**（誰看過我、投遞狀態、訊息） |
| 信任 | 平台不碰帳密 | **不存帳密**，借用使用者本機 Chrome 的登入態 |

因為信任模型不同，本案是**全新獨立地端程式**，與雲端版徹底分離。

### 完整願景（非本 MVP，僅記錄方向）

使用者最終想要的是：一個聊天介面邊聊邊整理履歷與求職偏好；agent 每天自動看 104
上的「誰看過我」、投遞/面試狀況，自動上網查公司評價，面試邀約確定日期自動進
行事曆；使用者每天只需專注在自己的行程與優化履歷。

這是一個太大、塞不進單一 spec 的構想，已拆成獨立子系統，各走「spec → plan → 實作」：

1. **地端執行殼 + 104 登入抓取**（← 本 MVP，已把「憑證保險箱」用持久化 Chrome profile 取代）
2. 對話式履歷/需求整理（聊天介面）
3. Agent 核心（每日 loop + 工具編排 + 推薦）
4. 公司評價 web 研究
5. 行事曆整合（面試邀約自動進 Google Calendar）
6. 每日彙整報告

### 本 MVP 的目標

打掉整個構想**最大的未知數**：到底能不能讀到使用者 104 登入後的私人資料。
做一條最薄但完整的管線，證明：**能登入、能讀到三類資料、能存快照比對變化、能 LLM 彙整**。

成功定義：使用者在本機跑 `career-sentinel run`，終端機印出「跟上次比有什麼變化」
（新增幾家看過你、哪筆投遞狀態變了、有沒有新面試邀約）+ 一段白話今日彙整。

### 非目標（Out of scope，留給後續子專案）

- 對話式履歷整理、公司評價 web 研究、面試邀約**自動進行事曆**、web UI。
- 每日**自動排程**（MVP 先手動 `run`；未來接 Windows 工作排程器 / cron 呼叫 CLI 即可）。
- 104 以外的求職網站。
- **不存任何帳密**（用持久化 Chrome profile 取代帳密儲存）。
- 推薦引擎、反向匹配延伸抓取（誰看過我 → 抓他們其他缺）。

## 技術選型（已與使用者確認）

| 項目 | 選擇 | 理由 |
|------|------|------|
| 語言 | Python | 使用者最熟、可沿用現有 LLM provider 抽象與 crawler 測試風格 |
| 介面 | CLI（MVP） | 最快驗證可行性；對話/web UI 留待後續子專案 |
| 瀏覽器自動化 | Playwright（Python） | 驅動真實 Chrome、能攔截網路請求 |
| 登入態 | **專用 Chrome profile + 首次手動登入 + session 持久化** | 不存帳密、不跟日常 Chrome 搶 profile lock，最穩 |
| 資料抽取 | **攔截 104 自身 XHR/JSON 為主、DOM 後援** | 結構化、最不怕改版；DOM 當退路 |
| 儲存 | SQLite | 地端單人、零維運、支援快照比對 |
| LLM | 自帶 key（`.env`），沿用 provider 抽象 | 地端使用者自負成本 |

## 架構總覽

一次使用的生命週期：

```
career-sentinel login   ← 只第一次：開專用 Chrome profile，使用者手動登入 104（含驗證碼）
career-sentinel run     ← 平常每天跑：
   開啟持久化 Chrome context（已登入）
        ↓
   三個讀取器（攔截 104 自己打的 XHR/JSON，DOM 當後援）
     ├─ 誰看過我
     ├─ 我的投遞狀態
     └─ 與公司訊息（含面試邀約）
        ↓
   正規化成型別模型 → 存進 SQLite（這次快照）
        ↓
   跟「上一次快照」比對 → 算出新增/變動
        ↓
   差異 + 現況 丟給 LLM → 產出「今日彙整」
        ↓
   印在終端機（變化清單 + 一段白話總結）
```

## 模組邊界

每個模組一個清楚職責、透過明確介面溝通、可獨立理解與測試。

| 模組 | 職責 | 介面（對外） | 依賴 |
|------|------|------|------|
| `browser` | 管理專用 Chrome profile，交出「已登入的 Playwright page/context」；偵測未登入就擋下並提示 `login` | `open_context()`、`ensure_logged_in() -> bool` | Playwright |
| `scraper` | 三個讀取器，各自「攔截 JSON 為主、DOM 後援」→ 回傳型別化資料。**抓取與解析函式分離** | `read_viewers()`、`read_applications()`、`read_messages()` | browser |
| `store` | SQLite 存每次快照、算差異 | `save_snapshot(data)`、`diff_against_last() -> Diff` | sqlite3 |
| `digest` | 把差異+現況交給 LLM 產生白話彙整；自帶 key | `summarize(diff, snapshot) -> str` | LLM provider |
| `cli` | `login` / `run` 兩個指令，串起流程 | argparse / typer 進入點 | 全部 |

**抓取與解析分離**：每個讀取器拆成「抓原始回應（需真瀏覽器、不可單測）」與
「純解析函式（吃原始 JSON/HTML → 型別模型，可單測）」，對應現有 crawler
`parse_jobs` / `parse_job_detail` 的做法。

## 資料模型（SQLite）

每次 `run` 寫一筆 `snapshots`，底下三張表各掛 `snapshot_id`，每列留一份 `raw_json`
（版面/欄位變了仍可回溯）：

```sql
snapshots(id INTEGER PK, run_at TEXT)              -- 一次 run 一列

viewers(snapshot_id, company, job_title, viewed_at, raw_json)
applications(snapshot_id, job_id, company, title, status, applied_at, raw_json)
messages(snapshot_id, thread_id, company, last_message, has_interview_invite,
         invite_date, raw_json)
```

差異（`diff_against_last`）= 比對**最近兩次快照**，以自然鍵判定新增/變動：
- viewers：自然鍵 `company + job_title`（或 104 提供的 viewer/job id，spike 時確認）→ 新增 = 新看過你的。
- applications：自然鍵 `job_id` → 變動 = `status` 改變。
- messages：自然鍵 `thread_id` → 新增訊息、或 `has_interview_invite` 由 false 轉 true。

`Diff` 是一個型別物件：`{ new_viewers, status_changes, new_messages, new_invites }`。

## 錯誤處理（沿用「單筆失敗跳過」的容錯哲學）

- **未登入 / session 過期**：`ensure_logged_in()` 偵測（被導去登入頁 / 預期回應拿不到）
  → 明確提示「請先跑 `career-sentinel login`」，不靜默失敗、不寫壞快照。
- **104 改版**：攔截抓不到 → 退回 DOM；兩者都失敗 → **該讀取器標記失敗、其他照跑**，
  最後報告哪一塊缺資料（不要一塊壞就全盤皆輸）。失敗的讀取器**不寫該類空資料**，
  以免污染下次差異比對。
- **LLM 失敗**：仍印出差異與現況，只標「今日彙整暫無」。
- **反爬**：單次循序、擬人操作、沿用現有節流心態（讀取器之間留間隔，不並發猛打）。

## 測試

- **解析函式**：用擷取下來的**假 JSON/HTML fixture** 測（不連線真 104），對應現有
  `parse_jobs` 注入假 session 的測試風格。涵蓋正常、欄位缺漏、空清單。
- **store/diff**：用合成的前後兩份快照測新增/變動/無變化。
- **手動 spike（實作第一步，無法單元測）**：連真 104，摸出三類資料各自的 XHR 端點、
  驗證持久化 profile 登入流程與 session 重用。spike 產出的真實回應存成 fixture 供上面單測。
- 沿用 pytest。

## 開放問題（實作時釐清，不阻擋設計）

- 三類資料的實際 104 XHR 端點與回應結構（spike 時摸出）。
- 104 是否對某些頁面採 server-render（需 DOM 而非攔截）——逐頁於 spike 確認。
- session 持久化的有效期（多久要重登一次）——實測觀察，過期由 `ensure_logged_in` 兜住。

## 後續

本 MVP 完成、實機驗證可讀到三類資料並產出每日彙整後，再依完整願景的子系統清單，
逐一 brainstorm 下一個子專案（建議順序：每日彙整報告強化 → 行事曆整合 → 對話式履歷整理）。
