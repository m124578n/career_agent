# 候選勾選 + 非同步逐筆分析 + 選地區 — 設計

日期：2026-06-22
狀態：已核可，待實作

## 目標

把目前「輸入關鍵字 → 後端爬取並自動分析前 5 筆」的綁定流程，改成**兩階段 + 非同步**：

1. **爬取候選**：爬 104 一頁（~30 筆）回候選清單（不花額度、不呼叫 LLM），標記每筆是否命中關鍵字（廣告→未命中）。
2. **勾選**：使用者在候選清單勾選要分析的（命中者預設勾、廣告預設不勾）。
3. **非同步分析**：對選中的逐筆背景分析，前端輪詢逐筆看到結果浮現。

同時新增**選地區**（縣市多選）作為爬取條件。

解決的痛點：104 搜尋結果夾帶不相關的廣告職缺（房仲、行政助理等），目前會被自動分析、白白消耗 LLM 額度。改由使用者勾選，準確且省額度。

## 範圍

- **本次**：兩階段流程、非同步逐筆分析 + 輪詢、選地區（縣市）。
- **不變**：求職追蹤清單（上一個 sub-project）、求職信、加入追蹤。
- **取代**：現有 `POST /jobs/searches`（爬+分析綁一起）與 `POST /jobs/searches/{id}/next`（分析下一批）改為本設計的兩階段端點。

## ⚠️ 已知限制（特別註記，須在 spec/程式碼/PROGRESS 標明）

1. **額度可能短暫超賣**：分析採「提交時檢查剩餘額度 ≥ 選中筆數、每筆 done 才 `quota.add(1)`」的寬鬆策略。背景任務尚在跑時若又送出新的分析，兩批的提交檢查都可能各自通過，導致實際完成數短暫超過每日上限。單人／小規模可接受；要嚴格需改成「提交時即佔額度」。**未來待辦**。
2. **背景任務不持久化**：逐筆分析用記憶體中的 asyncio 背景任務，**server 重啟會中斷未完成的任務**，那些職缺會卡在 `pending`。本期不做持久化續跑，靠前端對 `pending` 過久／`failed` 提供「重試」補救。**未來要韌性需上真正的 task queue（規劃文件提過）**。

## 流程與資料模型

### 資料模型變更

`matches` collection 文件新增兩欄：
- `status`：`candidate`（爬到待選）/ `pending`（已選排隊）/ `done`（完成有分數）/ `failed`（分析失敗）
- `relevant`：bool，關鍵字是否命中（廣告 → false，前端預設勾選用）

`JobMatch` schema（`schemas/__init__.py`）：
- `score: float` → 預設 0（candidate/pending 階段尚無分數）
- `reasons: list[str]` / `gaps: list[str]` → 預設空 list
- 新增 `status: str = "done"`（向後相容：既有資料視為 done）
- 新增 `relevant: bool = True`

`SearchRun` schema：
- 新增 `area: str | None = None`（縣市代碼，逗號分隔多選；None=全台）
- `next_offset` 改名語意為 `next_page`（已爬到第幾頁，初始 1，爬完一頁 →2）；爬下一頁用
- `count` = 候選總數

### crawler 變更

- `crawl_jobs(keyword, *, page=1, area=None, client=None)`：多帶 `area` 參數（104 搜尋 API 的 `area`，實測有效：`6001001000`=台北市、`6001006000`=新竹市）。
- 解析時為每筆算 `relevant`：
  - 主要信號：`jobNameSnippet`／`descSnippet` 含 `[[[`（104 對命中關鍵字的職缺會用 `[[[關鍵字]]]` 標出命中位置）。
  - fallback：關鍵字任一 token 字面出現在 `jobName`／`description`。
  - **只標記、不過濾**（過濾權交給使用者勾選）。
  - 回傳型別擴充為帶 relevant 的候選（例如 `parse_jobs` 回 `list[tuple[Job, bool]]`，或 Job 暫存 relevant 由 service 處理；實作時定，保持 crawler 純粹）。

## API（prefix `/jobs`）

| 方法 | 路徑 | 說明 |
|---|---|---|
| POST | `/searches` | body `{keyword, target, area?}`；建 SearchRun、爬第一頁、存 candidate placeholder（含 relevant），回 `{search_id, candidates}`。**不計額度、不呼叫 LLM**。 |
| POST | `/searches/{id}/crawl-next` | 爬下一頁（沿用 keyword/area，`next_page` 推進）、append candidate，回新增候選。 |
| POST | `/searches/{id}/analyze` | body `{job_ids}`；驗證 job_ids 屬該 search 的候選、檢查剩餘額度 ≥ 選中數（不足 429），把選中標 `pending`，啟動背景任務，立即回 `{queued: N}`。 |
| GET | `/searches/{id}/matches` | 回該 search 全部 match（含 status/relevant），供輪詢。 |
| GET | `/searches` | 歷史列表（不變）。 |
| DELETE | `/searches/{id}` | 刪除（cascade，不變）。 |
| POST | `/searches/{id}/cover-letter` | 求職信（不變；只對 done 的職缺）。 |

所有 `{id}` 端點沿用 `_ensure_owned`（擁有權驗證）。`analyze` 另驗 `job_ids` 確實屬該 search 的 candidate。

舊 `POST /searches/{id}/next` 移除。

## 額度

- `analyze` 提交時：`used_today + len(job_ids) > limit` → 429（明確訊息），不啟動任務。
- 每筆分析 `done` 後 `quota.add(1)`；`failed` 不計。
- 見上方「已知限制 1」。

## 背景任務與反爬

- **可注入的執行器**：analyze 端點呼叫一個 `AnalysisRunner.submit(search_id, user, job_ids, ...)`。預設實作用 `asyncio.create_task` 對 job_ids 逐筆序列處理（保留 2–5 秒節流）。測試注入同步 runner，驗證 status 轉換與額度。
- **全域 semaphore**：在抓 104 詳情處加一個 module-level `asyncio.Semaphore`（同時最多 1–2 個詳情請求），避免多個背景任務／多使用者併發打 104 被鎖。
- 單筆流程：candidate→pending（提交時）→ 抓詳情 + LLM → `done`（寫 score/reasons/gaps）或 `failed`。
- 見上方「已知限制 2」。

## 前端

### JobList 改兩階段
- 控制列：關鍵字輸入 ＋ **縣市多選**下拉（硬編縣市↔代碼對照表，不選=全台）＋「爬取」鈕。
- **候選清單**：每列含勾選框、職稱（連結）、公司、薪資、`relevant` 標記（命中亮／廣告標灰）。預設勾選 `relevant=true`、廣告不勾。「爬下一頁」append。
- 「分析選中（N 筆）」→ 送出 → 開始輪詢。
- 結果依 status 渲染：`pending` 轉圈卡 → `done` 分數卡（沿用現有 MatchCard：求職信、加入追蹤）→ `failed` 錯誤卡 ＋「重試」（重送該筆 analyze）。
- **輪詢**：有 `pending` 時 `useQuery` `refetchInterval` 2–3 秒；全部 done/failed 即停止輪詢。
- 版面：候選勾選區在上、已分析結果卡在下，沿用 Cockpit 暗色主題。

### 縣市代碼表
硬編一份台灣 22 縣市 ↔ 104 area 代碼（`6001` + 縣市序號 + `000`）。已驗證樣本：台北市 `6001001000`、新竹市 `6001006000`。**完整表於實作時從 104 實測／地區 API 取得並驗證**，避免放入未經驗證的代碼。

## 測試（TDD）

- **crawler**：`area` 參數帶入；`relevant` 標記（snippet `[[[` 命中、關鍵字字面 fallback、廣告→false）。
- **repository**：candidate placeholder 寫入與查詢、status 轉換、relevant 欄位。
- **analyze 端點**：job_ids 歸屬驗證、額度檢查（不足 429）、標 pending、呼叫注入的 runner。
- **背景 runner（同步注入版）**：candidate→pending→done/failed、逐筆 `quota.add(1)`、failed 不計、semaphore 行為。
- **爬取端點**：存 candidate、回候選、crawl-next 翻頁 append、area 帶入。
- **前端**：build ＋ 必要時 Playwright（候選勾選、預設勾選、提交、依 status 渲染、輪詢有 pending 才跑、重試）。

## 影響到的既有程式碼

- `crawler/__init__.py`：`crawl_jobs` 加 area；解析加 relevant。
- `schemas/__init__.py`：`JobMatch` 欄位 optional + status/relevant；`SearchRun` 加 area、next_page。
- `db/repositories.py`：`MatchRepository` 加 candidate 寫入、status 更新、按 status 查詢。
- `services/analyze.py`：拆成「爬取存候選」與「逐筆分析單筆」；新增可注入的 `AnalysisRunner` 與全域 semaphore。
- `api/routers/jobs.py`：`/searches` 改兩階段、新增 `/crawl-next`、`/analyze`，移除 `/next`。
- 前端 `client.ts`/`types.ts`、`JobList.tsx`（大改）、縣市代碼表。
