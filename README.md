# career_agent — 104 Job Tracker

AI 求職助手（多人，Google 登入）：上傳履歷 → 診斷優勢/缺口 → 爬 104 職缺 → 逐筆契合度排序 → 生成求職信 → 求職追蹤看板。

規劃文件：[104-job-tracker-規劃.md](104-job-tracker-規劃.md)
架構 spec：[docs/superpowers/specs/2026-06-21-104-job-tracker-架構-design.md](docs/superpowers/specs/2026-06-21-104-job-tracker-架構-design.md)
部署：[docs/DEPLOY.md](docs/DEPLOY.md)　進度：[docs/PROGRESS.md](docs/PROGRESS.md)

## 結構（monorepo）

```
career_agent/
├─ backend/    # FastAPI（Python / uv）— 見 backend/README.md
├─ frontend/   # React + Vite + TS + Mantine
├─ docs/       # 規劃、spec、部署、進度
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

## 快速開始

```bash
# 後端（讀 backend/.env，見 backend/.env.example）
cd backend && uv sync && uv run uvicorn job_tracker.main:app --reload

# 前端（VITE_API_BASE_URL 留空 → 走 Vite proxy /api → localhost:8000）
cd frontend && npm install && npm run dev

# 本地 MongoDB（或直接連 Atlas）
docker compose up -d
```

本機開發若不設 `GOOGLE_CLIENT_ID` 則停用登入（dev 模式，方便測試）。
