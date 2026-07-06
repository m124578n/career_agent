# career_agent — 104 Job Tracker

AI 求職助手：**上傳履歷 → 診斷優勢/缺口 → 搜 104 職缺 → 逐筆契合度排序 → 生成求職信 →
求職追蹤看板**。這個 repo 是 monorepo，含兩個版本：

| 版本 | 說明 | 目錄 |
|------|------|------|
| **雲端多人版**（本文件） | Google 登入即用、雲端部署、每人每日免費額度 | `backend/` + `frontend/` |
| **本機自架版 career-sentinel** | 地端、單人、自帶 key、資料留本機、含「求職總指揮」聊天 agent | [`sentinel/`](sentinel/README.md) |

線上網站的「本機自架」頁（`/self-host`）有自架版的完整啟動教學。

- 規劃文件：[104-job-tracker-規劃.md](104-job-tracker-規劃.md)
- 架構 spec：[docs/superpowers/specs/2026-06-21-104-job-tracker-架構-design.md](docs/superpowers/specs/2026-06-21-104-job-tracker-架構-design.md)
- 部署：[docs/DEPLOY.md](docs/DEPLOY.md)　進度：[docs/PROGRESS.md](docs/PROGRESS.md)

## 功能

- **履歷診斷**：對著目標職位，找出亮點與可加強處。
- **職缺契合度**：搜尋 104 職缺，逐筆比對履歷並排序（兩階段流程，見下）。
- **求職信生成**：依職缺與你的背景，一鍵生成可編輯的求職信。
- **投遞追蹤看板**：用看板管理投遞與面試進度、offer 一目了然。
- **多人 + 額度**：Google 登入、資料按使用者隔離、每人每日 LLM 呼叫上限。

## 結構（monorepo）

```
career_agent/
├─ backend/    # FastAPI（Python / uv）— REST API + 104 爬蟲 + LLM，見 backend/README.md
├─ frontend/   # React + Vite + TS + Mantine（Cloudflare Pages）
├─ sentinel/   # 本機自架版 career-sentinel（獨立子專案，見 sentinel/README.md）
├─ docs/       # 規劃、spec、部署（DEPLOY.md）、進度（PROGRESS.md）
└─ docker-compose.yml   # 本地 MongoDB
```

## 技術選型

| 層 | 技術 |
|----|------|
| 後端 | FastAPI、MongoDB（motor）、curl_cffi（爬 104）、可抽換 LLM provider 層 |
| 前端 | React + Vite + TypeScript + Mantine、React Router、TanStack Query、Google OAuth |
| LLM | 預設 Azure AI Foundry 上的 Claude（`LLM_PROVIDER` 可切 Foundry / Azure OpenAI / Anthropic / OpenRouter）|
| 部署 | Cloudflare Pages（前端）+ Zeabur（後端，Docker）+ MongoDB Atlas（DB）|

## 重點設計

- **104 爬蟲走 curl_cffi（Chrome TLS 指紋）**：104 的 WAF 會用 TLS 指紋（JA3）擋掉非瀏覽器的請求，
  連雲端機房 IP 的 Linux 預設 TLS 都會被 403。改用 `curl_cffi` 模擬 Chrome 的 TLS 指紋後，
  雲端可直接同步爬 104，無需任何本機程序或代理。
- **兩階段職缺流程**：先爬候選（不花額度）→ 勾選有興趣的 → 背景逐筆抓詳情 + LLM 分析排序（節流護 104）。
- **多人 + 額度**：Google 登入、資料按 user 隔離、每人每日 LLM 呼叫上限（`DAILY_CALL_LIMIT`）。
- **LLM provider 抽象層**：切換只改 `.env` 的 `LLM_PROVIDER`；新增 provider = 加一個 class。

## 快速開始（本機開發）

```bash
# 1. 本地 MongoDB（或直接連 Atlas，跳過這步）
docker compose up -d

# 2. 後端（讀 backend/.env，見 backend/.env.example）→ http://localhost:8000（文件 /docs）
cd backend && uv sync && cp .env.example .env && uv run uvicorn job_tracker.main:app --reload

# 3. 前端（VITE_API_BASE_URL 留空 → 走 Vite proxy /api → localhost:8000）→ http://localhost:5173
cd frontend && npm install && npm run dev
```

本機開發若不設 `GOOGLE_CLIENT_ID`（後端）/ `VITE_GOOGLE_CLIENT_ID`（前端）則**停用登入**（dev
模式，方便測試）。詳細後端說明見 [backend/README.md](backend/README.md)。

### 環境變數（後端 `backend/.env`）

| 變數 | 說明 |
|------|------|
| `MONGO_URI` / `MONGO_DB` | MongoDB 連線字串與資料庫名 |
| `ALLOWED_ORIGINS` | CORS 白名單（前端網址，逗號分隔） |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID（留空＝停用登入） |
| `DAILY_CALL_LIMIT` | 每人每日 LLM 呼叫上限（預設 50） |
| `ADMIN_EMAILS` | 可看全站 token 用量的 email（逗號分隔） |
| `LLM_PROVIDER` | `foundry` / `openrouter` / `azure_openai` / `anthropic` |
| `FOUNDRY_*` / `OPENROUTER_*` / `AZURE_OPENAI_*` / `ANTHROPIC_*` | 對應 provider 的 key/endpoint/model |
| `LOG_LEVEL` | 日誌等級（預設 `INFO`） |

前端只需 `VITE_API_BASE_URL`（正式環境）與 `VITE_GOOGLE_CLIENT_ID`。

## 測試

```bash
cd backend && uv run pytest        # 後端
cd frontend && npm run build       # 前端型別/建置檢查
```

## 部署

**前端 Cloudflare Pages + 後端 Zeabur（Docker）+ DB MongoDB Atlas**，push `main` 自動觸發。
完整步驟（含 Google OAuth、CORS 回填、環境變數對照）見 **[docs/DEPLOY.md](docs/DEPLOY.md)**。

> **分支慣例**：日常開發在 `dev` 分支，驗證 OK 才合併進 `main`。只有 `main` 觸發正式部署；
> push `dev` 不動後端，Cloudflare 給 preview URL。

## 本機自架版

想在自己電腦上跑、資料完全留本機、並用「求職總指揮」聊天 agent 跑完整條求職流程？
見 **[sentinel/README.md](sentinel/README.md)**。
