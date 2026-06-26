# 104 Job Tracker — 開發進度

> 最後更新：2026-06-25
> 規劃文件：[../104-job-tracker-規劃.md](../104-job-tracker-規劃.md)
> 架構 spec：[superpowers/specs/2026-06-21-104-job-tracker-架構-design.md](superpowers/specs/2026-06-21-104-job-tracker-架構-design.md)

這份是進度快照，記錄已完成、進行中、待辦。新進度往對應區塊加。

---

## 技術選型（已定案）

| 層 | 選擇 |
|----|------|
| 後端 | FastAPI（Python 3.14 / uv） |
| 前端 | React + Vite + TypeScript + Mantine（React Router + TanStack Query） |
| 爬蟲 | httpx 純 HTTP（104 有 JSON API，不需 Playwright） |
| 資料庫 | MongoDB（motor） |
| LLM | 可抽換 provider 層：OpenRouter / Azure OpenAI / Anthropic |
| 部署 | Cloudflare Pages（前端）+ Zeabur（後端）+ MongoDB Atlas |

---

## ✅ 已完成

### 專案骨架
- monorepo：`backend/`（FastAPI，src layout）+ `frontend/`（Vite）
- `docker-compose.yml` 本地 MongoDB；`.env.example` 範本
- 前後端各自 `uv sync` / `npm install` 驗證可 build

### 後端功能（皆 TDD，27 測試全綠）
- **爬蟲（M4 抓取）**：`crawler/`
  - `crawl_jobs` 打 104 搜尋 JSON API（需 Referer header）
  - `fetch_job_detail` / `crawl_job_details` 抓完整 JD + 薪資 + 條件需求
  - **反爬節流**：詳情逐筆抓、請求間隨機延遲 2–5 秒
- **存 DB**：`db/repositories.py` + `services/ingest.py`
  - `JobRepository`（以 job_id upsert，含 detail 子文件）
  - `ingest_jobs`：爬搜尋 → 存 → 抓詳情（節流）→ 存
  - 真實 Mongo 驗證 32 筆 ingest 成功
- **M2 履歷診斷**：`services/resume_diagnosis.py` → `POST /api/resumes/diagnose`
- **M4 契合度分析**：`services/job_matching.py`（LLM 分析 + 規則層外部投遞旗標 → 排序）
- **M5 求職信**：`services/cover_letter.py`（自由文字產生）
- **API**：`/health`、`/api/resumes/{parse,diagnose}`、`/api/jobs`（list + crawl）

### LLM provider 抽象層（`llm/`）
- `base.py` 介面 + `providers.py` 實作 + `_REGISTRY` + `make_provider`
- 切換只改 `.env` 的 `LLM_PROVIDER`；新增 provider = 加一個 class
- 四個 provider（兩條基底）：
  - OpenAI 相容基底（json_object + schema 塞 prompt + Pydantic 驗證）：
    - **OpenRouter**、**Azure OpenAI**
  - Anthropic 原生基底（messages.parse + adaptive thinking）：
    - **Anthropic**（直連）、**Foundry**（Azure AI Foundry 上的 Claude，端點 `.../anthropic`）
- ✅ **真實驗證通過**：Azure Foundry + Claude Sonnet 4.6 跑履歷診斷，結構化輸出正常、中文品質佳

---

## 🚧 進行中 / 卡關

- （無）LLM 已用 Azure Foundry Claude Sonnet 4.6 驗證通過。
  - OpenRouter 免費模型曾持續被限流（429）→ 放棄走免費，改 Azure。
  - 目前 `.env` 設 `LLM_PROVIDER=foundry`，`FOUNDRY_BASE_URL=.../anthropic`、`FOUNDRY_MODEL=claude-sonnet-4-6`。

---

## 🎨 前端設計系統（Cockpit 指揮艙）

- 深色 ink 底 + 雙訊號色（tangerine 行動 / teal 契合）+ 終端機式 mono 標籤
- 字型：Space Grotesk(標) / IBM Plex Sans(內文) / IBM Plex Mono(數據)
- 樣式集中在 `frontend/src/styles/global.css`（`.jt-*` 前綴），Mantine 主題在 `theme.ts`
- ✅ **履歷與目標頁完成並 e2e 驗證**：上傳 PDF → 解析 → 執行診斷 → 讀數面板
  （[+] 優勢 / [!] 待補強），用真實履歷 + Azure Foundry Claude Sonnet 4.6 跑通
- ✅ **職缺契合度頁完成並 e2e 驗證**：輸入關鍵字 → 爬取 + 逐筆分析 → 排序卡片
  （契合度能量條、teal 分數、[+]/[!] 標籤）。履歷目標跨頁共用（ResumeContext + localStorage）

### 後端契合度流程（M4）
- `services/analyze.analyze_jobs`：爬 → 逐筆詳情（節流、**容錯**：單筆失敗跳過）→ LLM 分析 → 存 DB → 排序
- `JobRepository.set_match/list_matches`；API `POST /api/jobs/analyze`、`GET /api/jobs/matches`

### 求職信（M5）✅ 完成並 e2e 驗證
- `cover_letter.generate`（用完整 JD + 履歷）；API `POST /api/applications/cover-letter`
- 前端：每張職缺卡「生成求職信」→ modal（可編輯、重新生成、複製）

### Logging ✅ 基礎 + 請求計時
- `logging_config.setup_logging`（`LOG_LEVEL` 環境變數、乾淨格式、stdout）
- 啟動（provider/model/db）、爬蟲（keyword/page/count）、LLM 呼叫（model/延遲/ok-fail）、
  analyze（start/done）、每個 HTTP 請求（method/path/status/耗時）
- 已實際驗證 log 輸出正常

### Token 用量記錄 ✅ 完成並驗證
- `llm/usage.py`：可插拔 sink（單元測試 no-op，app 啟動時接 Mongo）；正規化 OpenAI/Anthropic usage
- providers 每次呼叫後記錄；`TokenUsageRepository`（record/summary by_model）
- API `GET /api/usage`；前端側欄底部顯示總 token / 呼叫次數（每 15 秒更新）
- 實測：診斷一次記錄 965 tokens（claude-sonnet-4-6）寫入 Mongo

### 資料庫 ✅ 已上 MongoDB Atlas
- `.env` 的 `MONGO_URI` 指向 Atlas（`mongodb+srv://...career-agent...`），已驗證 ping/讀寫 OK
- 本機 `docker-compose` 的 Mongo 仍保留供離線開發；正式用 Atlas M0（免費）
- ⚠️ 部署到 Zeabur 時：Atlas 要把 Zeabur 出口 IP 加進 Network Access 白名單
  （或暫用 0.0.0.0/0 + 強密碼），否則連不上

### 部署設定 ✅ 已備好（待實際上線）
- 後端 `backend/Dockerfile`（uv + Python 3.14，無 Playwright，~510MB）+ `.dockerignore`
  - 本機 `docker build` + run 驗證過：`/health` ok、綁 `PORT`、啟動日誌正常
- CORS 改 `ALLOWED_ORIGINS` 環境變數（逗號分隔）
- 前端 `VITE_API_BASE_URL` 環境變數控制 API 網址；`public/_redirects` 處理 SPA 路由
- 步驟見 [DEPLOY.md](DEPLOY.md)（Zeabur 後端 + Cloudflare Pages 前端 + Atlas）

### 認證 + 多人 + 額度 ✅ 完成
- **Google 登入**：`auth.current_user` 驗 Google ID token（`google-auth`）；`GOOGLE_CLIENT_ID` 未設時停用（本機/測試）
- **每日額度**：`QuotaRepository` 每人每日 LLM 呼叫數；超過 429（預設 50/日）。診斷/求職信=1、分析=實際筆數（單次上限 10）
- **資料隔離**：`MatchRepository` 契合度結果按 user 分開（獨立 `matches` collection）；
  `token_usage` 也按 user（contextvar 在請求層帶 user 給解耦的 LLM 記錄層）
- **API**：`GET /api/usage`（個人 token）、`/usage/global`（**僅 admin**）、`/usage/quota`（含 is_admin）；所有 `/api` 需登入
- **admin**：`ADMIN_EMAILS` 名單可看全站用量；前端側欄 admin 多顯示「全站 tokens」
- 測試用 `conftest.py` 強制 dev 設定，不受開發者 `.env` 影響
- **前端**：`@react-oauth/google` 登入閘門、Bearer header、401 自動登出；側欄顯示今日額度 + 使用者 + 登出
- 55 測試全綠；dev 模式（無 client id）免登入照常用，已截圖驗證

## ✅ 已修 / 已調整（使用者回報 2026-06-21，於 2026-06-22 完成）

1. ✅ **求職信顯示 + 存 DB**：生成的求職信存到該使用者 match（`✎ 已寫求職信` 標記、可重看不重生）；
   loading 改清楚（秒數 + 鎖 modal），避免等待中誤關。
2. ✅ **進度顯示**：`AnalyzingSteps` 共用元件——階段文字依序跳出（終端機序列風）+ 經過秒數，
   履歷診斷與職缺分析都套用。
3. ✅ **翻下一批**：`analyze_jobs` 改 offset 累進；前端「分析下一批（第 N–M 筆）」按鈕。

## ✅ 搜尋歷史 + 求職追蹤清單（2026-06-22 完成核心，TDD subagent-driven）

對應 spec [superpowers/specs/2026-06-22-search-history-and-tracking-design.md](superpowers/specs/2026-06-22-search-history-and-tracking-design.md)、
plan [superpowers/plans/2026-06-22-search-history-and-tracking.md](superpowers/plans/2026-06-22-search-history-and-tracking.md)。後端 78 測試全綠。

- **搜尋歷史（search runs）**：每次「爬取並分析」＝一筆 `SearchRun`（存 keyword + target 快照 + next_offset + count），
  不再 destructive clear。可在歷史 chips 間切換回顧、在舊歷史上「分析下一批」、手動刪除單筆（cascade 刪其 matches）。
  - 資料模型：`SearchRepository`（searches collection）；`MatchRepository` 改以 `search_id|job_id` 為主鍵綁定到 search。
  - 端點：`POST/GET /api/jobs/searches`、`POST /searches/{id}/next`、`GET /searches/{id}/matches`、
    `DELETE /searches/{id}`、`POST /searches/{id}/cover-letter`（求職信端點從 applications 移來，並驗證 search 擁有權）。
- **求職追蹤清單**：求職信 modal 生成完成後「加入追蹤」（job 與求職信**快照**寫入，來源 search 刪了也不影響）。
  - 資料模型：`ApplicationRepository`（applications collection，以 `user|job_id` 去重），五階段狀態 +
    `events` 時間軸骨架（本期只記狀態變更）。
  - 端點：`POST/GET /api/applications`、`PATCH /applications/{job_id}`（改狀態、append event）、`DELETE`。
  - 前端：`/applications` 五欄看板（待投遞 → 已投遞 → 面試中 → Offer → 結束），下拉改狀態、移除。
- **下個 sub-project（未做）**：面試多輪**時間軸**、**面試筆記**、看板**拖拉** UI（events 資料骨架已備）。

## ✅ 候選勾選 + 非同步逐筆分析 + 選地區（2026-06-23 完成，TDD subagent-driven）

對應 spec [superpowers/specs/2026-06-22-candidate-selection-async-analyze-design.md](superpowers/specs/2026-06-22-candidate-selection-async-analyze-design.md)、
plan [superpowers/plans/2026-06-22-candidate-selection-async.md](superpowers/plans/2026-06-22-candidate-selection-async.md)。後端 89 測試全綠。

把「爬取即分析」改成**兩階段**，解決 104 搜尋夾帶廣告職缺（房仲/行政等）白白燒額度的問題：

- **爬取候選**：`POST /api/jobs/searches {keyword, target, area?}` 爬 104 一頁（~30 筆），存成 `candidate` placeholder，**不花額度、不呼叫 LLM**。每筆標 `relevant`（104 的 `[[[關鍵字]]]` 命中標記或關鍵字字面），廣告→false。`POST /searches/{id}/crawl-next` 爬下一頁。
- **勾選**：前端候選清單（Checkbox），預設勾命中、廣告標「廣告？」不勾。
- **非同步逐筆分析**：`POST /searches/{id}/analyze {job_ids}` 把選中標 `pending` 立即回 `{queued}`；背景 `AsyncioRunner` 逐筆（`analyze_one`：抓詳情經全域 `DETAIL_SEMAPHORE`→LLM→`done`/`failed`），每筆 done 才計 1 額度、失敗不計。前端 `refetchInterval` 輪詢，逐筆從 pending→done 浮現，failed 可重試。
- **選地區**：縣市多選（`crawl_jobs` 帶 104 `area` 參數）。前端 `constants/regions.ts` 硬編 20 縣市代碼（新竹/嘉義縣市合併），已實測驗證。
- 資料模型：`JobMatch` 加 `status`/`relevant`（分數 optional）；`SearchRun` 加 `area`/`next_page`；`MatchRepository` 加 candidate/status 方法。

### ⚠️ 已知限制（待未來改進）
1. **額度可能短暫超賣**：提交檢查「剩餘 ≥ 選中數」+ 每筆 done 才計的寬鬆策略；背景跑時併發送出可能微幅超量。要嚴格需改「提交時即佔額度」。
2. **背景任務不持久化**：逐筆分析用記憶體 asyncio task，**server 重啟會中斷未完成的、卡在 pending**，靠前端重試補救。要韌性需上真正的 task queue。

## ✅ 104 改用 curl_cffi（Chrome TLS 指紋）雲端直接爬（2026-06-26 定案）

> 重要更正：先前曾誤判 104 是「機房 IP 封鎖」，並為此蓋了一整套**本機爬蟲 agent + MongoDB
> 任務隊列**子系統。實測後確認**真正的原因是 TLS 指紋（JA3）**，不是 IP——
> 診斷端點從同一個機房 IP（Zeabur）測：httpx（Linux 原生 TLS）403、curl_cffi（Chrome TLS）**200**。
> 故 agent 子系統已**整套移除**，改用最簡解：crawler 用 `curl_cffi` 模擬 Chrome TLS 指紋，
> 雲端直接同步爬 104，不需任何本機程序。

- **crawler（`crawler/__init__.py`）**：`crawl_jobs` / `fetch_job_detail` / `crawl_job_details`
  改用 `curl_cffi.requests.AsyncSession(impersonate="chrome")`，連 TLS/JA3 都裝成 Chrome；
  純解析函式（`parse_jobs` / `parse_job_detail` / `_is_relevant` / `_format_salary`）不變。
  測試用可注入的假 session（不再依賴 httpx MockTransport）。
- **流程回到同步**：`create_search` 直接爬並回候選；`analyze_selected` 用 `AsyncioRunner` 背景逐筆
  `analyze_one`（抓詳情 → LLM → 寫結果，經 `DETAIL_SEMAPHORE` 節流）。前端 UX 同步、即時。
- **移除**：`agent/` 目錄、`/api/agent/*` 端點、`crawl_tasks` 隊列、`CrawlTaskRepository` /
  `AgentStatusRepository`、`SearchRun.crawl_status`、`AGENT_SECRET` 設定、前端 agent 指示燈/輪詢。
- 後端 103 測試全綠；本機與雲端（同機房 IP）curl_cffi 實測皆 200。

## 🔲 待辦（backlog）
- **實際上線**：照 DEPLOY.md 在 Zeabur / Cloudflare 建 service、填環境變數、串 CORS + Google OAuth
- **M6 外部投遞提醒**：規則已有（`external_apply`），卡片已標「需官網投遞」，可再做提醒清單
- **批次體驗**：翻下一批、已看/已投標記；求職進度看板
- **求職信端點**：`cover_letter` 服務有了，缺 API 端點
- **pipeline 接成端點**：`pipeline.run_batch`（爬→分析）串成 API 並把結果落 DB
- **M3a 關鍵字優化**（P1）、**批次體驗強化**（翻下一批、已看/已投標記）
- **部署**：Dockerfile（後端）、Cloudflare Pages、MongoDB Atlas

---

## 註記 / 踩雷

- 環境用 Windows，Git Bash + PowerShell 並用；行尾 LF↔CRLF 警告無害。
- OpenRouter 有兩種金鑰：**Provisioning（管理用）不能做推論**，要用一般 Inference key。
- 免費模型清單會輪替，`google/gemini-2.0-flash-exp:free` 已下架。
- Azure 坑：`DEPLOYMENT` 是部署名稱（不是模型名）；`ENDPOINT` 結尾 `.openai.azure.com` 不加路徑。
