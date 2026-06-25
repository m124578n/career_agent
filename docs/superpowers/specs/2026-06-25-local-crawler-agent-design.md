# 本機爬蟲 agent — 設計

> 日期：2026-06-25
> 狀態：設計定案，待寫實作計畫
> 相關：[PROGRESS.md](../../PROGRESS.md)、爬蟲現況 `backend/src/job_tracker/crawler/__init__.py`

## 背景與問題

104 依**出口 IP** 封鎖爬蟲。實測確認：

| 來源 | 同一份程式碼、同樣 headers | 結果 |
|------|------|------|
| 本機（住宅 IP） | UA + Referer（甚至純 httpx） | HTTP 200 |
| 正式機（Zeabur 機房 IP） | 完整 Chrome 指紋 + cookie 暖身 | HTTP 403 |

結論：這是**硬 IP 封鎖**，發生在網路/WAF 層。加 header 偽裝、改用動態（瀏覽器）爬蟲都無效——因為請求仍從被封的機房 IP 出去，且住宅 IP 用純 HTTP（無 JS）就成功，代表 104 沒有「需要瀏覽器執行 JS」那道關，唯一的差別變數是 IP。

**唯一能改變結果的是換出口 IP 成住宅 IP。** 在「免費 + 即時結果 + 給朋友用」的條件下，唯一可行解是：把「打 104」這一步搬到家用住宅 IP 的本機 agent 上跑，雲端後端負責 API / DB / LLM / 排序。

## 目標與非目標

**目標**
- 雲端服務維持對外可用（登入、分析、求職信、追蹤清單全留雲端）。
- 「爬 104」改由家用住宅 IP 的本機 agent 代打，繞過機房 IP 封鎖。
- 朋友送出搜尋時，agent 離線則任務排隊，agent 上線後自動跑完。
- 不花錢（不用付費 proxy）。

**非目標**
- 不追求「爬蟲 24h 隨時可用」——agent 是使用者的電腦，需要時才開，離線是正常狀態。
- 不解決 104 ToS / 法律層面的定位（屬產品決策，非本設計範圍）。
- 不做付費 residential proxy 整合（未來若要服務化再議）。

## 約束條件（來自 brainstorming）

- **agent 主機**：使用者的電腦，需要時才手動開。經常離線。
- **通訊方式**：輪詢任務隊列，隊列存 MongoDB（複用現有 Mongo）。
- **離線行為**：任務進 queue 排隊等待，agent 上線後自動跑完；前端顯示「排隊中·等爬蟲上線」。

## 架構總覽

```
朋友 → 前端(Cloudflare) → 雲端後端(Zeabur)
                                │  enqueue 任務
                                ▼
                    MongoDB crawl_tasks（pending 任務隊列）
                                ▲ claim / complete
                                │
                    本機 agent（住宅 IP，需要時才開）
                                │ 抓 104 → 回原始 JSON
                                ▼
        雲端：parse → relevant → 存 DB → LLM 分析 → 排序
```

### 關鍵邊界：agent 是「笨」的住宅 IP 取數器，不做解析

agent 只負責：拿到「要打哪個 104 請求」的任務 → 用住宅 IP 發 GET（帶完整 header + cookie 暖身 + 節流）→ 把 104 回的**原始 JSON 原封不動回傳**。所有解析、relevant 判定、存 DB、LLM 分析全留雲端。

理由：
- agent 極小、無狀態，使用者開機跑一個 script 即可，依賴最少。
- 解析邏輯只存在雲端一處（複用現有 `parse_jobs` / `parse_job_detail`），改解析不必重發 agent。
- 任務內容單純（搜尋 params 或詳情 code），好除錯。

## 元件

### 1. MongoDB 任務隊列（新 collection `crawl_tasks`）

任務文件欄位（草案）：

| 欄位 | 說明 |
|------|------|
| `task_id` | 主鍵 |
| `type` | `search` \| `detail` |
| `payload` | search：`{keyword, page, area}`；detail：`{code}` |
| `status` | `pending` \| `claimed` \| `done` \| `failed` \| `expired` |
| `result` | 完成時存 agent 回填的原始 JSON（done 後雲端解析用完可清） |
| `error` | failed 時的原因 |
| `search_id` | 關聯的 SearchRun（雲端解析結果時要綁回去） |
| `created_at` / `claimed_at` / `completed_at` | 時間戳，供過期與回收判斷 |

任務型別對應現有打 104 的兩處：

| 任務型別 | payload | 對應現有函式 |
|---------|---------|------------|
| `search` | keyword, page, area | `crawl_jobs` |
| `detail` | job code | `fetch_job_detail` |

### 2. 雲端 agent 端點（新，機器對機器，獨立於使用者登入）

- `POST /api/agent/claim` — 原子認領一個 pending 任務（`findOneAndUpdate` pending→claimed），回任務內容；無任務回空。順便更新 agent `last_seen` 心跳。
- `POST /api/agent/complete` — 回填 `{task_id, raw_json}` 或 `{task_id, error}`；雲端據此解析存 DB 或標 failed。
- `GET /api/agent/status` — 給前端讀「最近 N 秒內是否有心跳」，判斷爬蟲在線/離線。

認證：共享密鑰 `AGENT_SECRET`（雲端環境變數一份、agent 一份）。agent 請求帶 `Authorization: Bearer <secret>`，`/api/agent/*` 驗此密鑰，與使用者 Google 登入分離。密鑰錯回 401。

### 3. 本機 agent（新增 `agent/` 獨立小專案）

- 一個 Python script，極簡依賴（httpx + 讀環境變數）。**不依賴 MongoDB、不 import job_tracker 套件**。
- 主迴圈：`claim` → 沒任務則 sleep 幾秒再問 → 有任務就抓 104 → `complete`。
- 設定（環境變數 / `.env`）：`CLOUD_BASE_URL`、`AGENT_SECRET`、輪詢間隔、節流秒數。
- 住宅 IP 抓法（完整 Chrome 指紋 header + cookie 暖身 + detail 任務間隨機節流 2–5 秒）放在 agent 這邊。

### 4. 雲端 crawl 流程改造

原本「同步直接打 104」改成「丟任務進隊列 + 前端輪詢等結果」：

- `POST /api/jobs/searches`：不再直接 `crawl_jobs`，改為建立 SearchRun + enqueue 一個 `search` 任務，立刻回 `{search_id, status: "queued"}`。
- `POST /searches/{id}/crawl-next`：enqueue 下一頁的 `search` 任務。
- `POST /searches/{id}/analyze`：選中的每筆 enqueue 一個 `detail` 任務；agent 回填詳情後，雲端走現有 LLM 分析流程。
- 節流移到 agent 端，雲端不再需要 `crawl_job_details` 的延遲邏輯（或保留供未來本機直連模式）。

## 資料流：搜尋的完整生命週期

```
1. 朋友按「爬取候選」
   → POST /api/jobs/searches：建 SearchRun + enqueue search 任務(pending) → 回 {search_id, queued}
2. 前端輪詢 GET /searches/{id}（沿用現有 refetchInterval）
   → queued/處理中 → 顯示「排隊中·等爬蟲上線」
3. 使用者開電腦，agent 啟動
   → POST /api/agent/claim（帶密鑰）→ 原子認領 → 用住宅 IP 抓 104 → POST /api/agent/complete{raw_json}
4. 雲端收結果 → parse_jobs 解析 → 標 relevant → 存 candidates → 任務標 done
5. 前端輪詢 → candidates 出現 → 朋友勾選 → 「分析選中」
   → 每筆 enqueue detail 任務 → agent 逐筆抓（節流）→ 雲端 LLM 分析 → 排序
```

任務狀態機：`pending → claimed → done`（或 `failed`）。`pending` 逾時 → `expired`；`claimed` 逾時未完成 → 退回 `pending`。

## 錯誤處理與邊界

- **agent 抓 104 失敗（403 / 網路）**：回填 `failed` + 原因 → 雲端標該任務 failed → 前端沿用現有 failed 重試 UI。
- **agent crash / 關機**：任務停在 `claimed`；回收機制將 `claimed` 超過 X 分鐘未 `complete` 的退回 `pending`，避免卡死。
- **任務過期**：`pending` 超過 24h 未被認領標 `expired`，避免久未開機後一次跑完一堆過時搜尋；前端對 expired 顯示「已過期，請重新搜尋」。
- **密鑰錯**：雲端回 401，agent log 明確報錯。
- **離線偵測**：agent 每次 claim 更新 `last_seen`；`GET /api/agent/status` 回最近是否有心跳 → 前端顯示在線/離線指示燈。

## 前端改動

- **爬蟲狀態指示燈**（🟢 在線 / ⚪ 離線）：讀 `/api/agent/status`，放側欄或職缺頁。
- **排隊/爬取中狀態**：送出後候選區顯示 `排隊中·等爬蟲上線`（agent 離線）或 `爬取中…`（已認領），沿用現有 `AnalyzingSteps` 風格。
- **expired 顯示**：「已過期，請重新搜尋」。
- 「搜尋從同步變非同步輪詢」與現有「分析逐筆輪詢」是同一套 UX，保持一致。

## 測試策略

全部 TDD，沿用現有 MockTransport / 假 Mongo / conftest 強制 dev 設定的模式。

- **雲端**
  - 隊列 repository：enqueue、claim 原子性、complete、expire、claimed 回收。
  - agent 端點：認證（對/錯密鑰）、claim 回任務、complete 觸發解析存 DB、complete 帶 error 標 failed。
  - 改造後的 search 流程：POST searches 變成 enqueue + 回 queued。
- **agent**
  - 用 MockTransport 測「claim → 抓 → complete」迴圈、失敗回填、節流間隔。

## 未決 / 未來

- 數值待定（實作時決定合理預設）：輪詢間隔、`pending` 過期時間、`claimed` 回收時間、心跳判定離線的秒數。
- 未來若要「服務隨時可用」→ 評估付費 residential proxy（本設計的雲端隊列架構可沿用，只是改由雲端直連 proxy）。
- 多 agent / 任務優先序：目前單 agent 足夠，`findOneAndUpdate` 原子認領已預留多 agent 安全。
```

## 分支

開發在 `dev`，驗證 OK 才合 `main`（合 `main` 才觸發部署）。agent 是本機跑，不經部署。
