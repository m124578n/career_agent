# 104 Job Tracker — 開發進度

> 最後更新：2026-06-21
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
