# career_agent — 104 Job Tracker

單人用的 AI 求職助手：上傳履歷 → 診斷 → 爬 104 職缺 → 逐筆契合度排序 → 生成求職信。

規劃文件：[104-job-tracker-規劃.md](104-job-tracker-規劃.md)
架構 spec：[docs/superpowers/specs/2026-06-21-104-job-tracker-架構-design.md](docs/superpowers/specs/2026-06-21-104-job-tracker-架構-design.md)

## 結構（monorepo）

```
career_agent/
├─ backend/    # FastAPI（Python / uv）— 見 backend/README.md
├─ frontend/   # React + Vite + TS + Mantine
├─ docs/       # 規劃與 spec
└─ docker-compose.yml   # 本地 MongoDB
```

## 技術選型

| 層 | 技術 |
|----|------|
| 後端 | FastAPI、MongoDB（motor）、Playwright、Claude API |
| 前端 | React + Vite + TypeScript + Mantine、React Router、TanStack Query |
| 部署 | Cloudflare Pages（前端）+ Zeabur（後端）+ MongoDB Atlas（DB）|

## 快速開始

```bash
# 後端
cd backend && uv sync && uv run uvicorn job_tracker.main:app --reload

# 前端
cd frontend && npm install && npm run dev

# 本地 MongoDB
docker compose up -d
```
