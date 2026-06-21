# 104 Job Tracker — 資料夾架構與前後端技術選型

> 版本：v1.0
> 日期：2026-06-21
> 關聯文件：[104-job-tracker-規劃.md](../../../104-job-tracker-規劃.md)

---

## 1. 目標與範圍

為 104 Job Tracker（單人用 AI 求職助手）定義**資料夾架構**與**前後端技術選型**，
作為後續實作的地基。本文件只處理「怎麼擺、用什麼技術」，不涉及各模組的演算法細節
（那些在規劃文件的 M1～M6）。

### 已定案的技術選型

| 層 | 選擇 | 理由 |
|----|------|------|
| 後端 | **FastAPI**（Python / uv，Python 3.14） | 最熟 |
| 前端 | **React + Vite + TypeScript + Mantine** | 取代原規劃的 Gradio；前後端分離；Mantine 元件齊全，dashboard 開發快 |
| 前端路由 | **React Router** | 頁面路由 |
| 前端資料層 | **TanStack Query** | 管 API 資料、loading/error/cache |
| 爬蟲 | **Playwright** | 104 反爬，Playwright 較穩 |
| LLM | **Claude API / OpenAI** | 契合度分析、求職信生成 |
| 資料庫 | **MongoDB**（motor async driver） | 職缺結構不固定；雲端用 MongoDB Atlas 免費 tier |
| 部署 | **Cloudflare Pages（前端）+ Zeabur（後端）+ MongoDB Atlas（DB）** | SaaS 省事省錢；後端含 Playwright 需容器，Zeabur 吃 Dockerfile；前端純靜態丟 Cloudflare Pages |

### 核心架構決策

- **前後端分離**：後端提供 REST API，前端是獨立 SPA 透過 HTTP 串接。
- **Monorepo**：前後端放同一個 repo 的 `backend/` 與 `frontend/` 子資料夾。單人專案、
  前後端常一起改，放一起最省事；之後真要拆再拆。
- **核心邏輯與 API 解耦**：`services/`、`crawler/`、`llm/` 不依賴 FastAPI，`api/` 只把它們
  包成 HTTP。爬蟲腳本、之後的批次任務可直接 import，不必透過 API。

---

## 2. Repo 整體架構

```
career_agent/
├─ backend/              # FastAPI（Python / uv）
├─ frontend/             # React + Vite + TS + Mantine
├─ docs/                 # 規劃文件、spec
├─ docker-compose.yml    # 本地起 MongoDB
├─ .gitignore
└─ README.md
```

> 現有 `uv init` 產生的 `main.py` / `pyproject.toml` / `.python-version` 會搬進 `backend/`。

---

## 3. Backend 內部結構（`backend/`）

採 src layout。模組對應規劃文件的 M1～M6：

```
backend/
├─ src/job_tracker/
│   ├─ main.py            # FastAPI app 進入點
│   ├─ config.py          # 設定（讀 .env：API keys、Mongo URI）
│   ├─ api/routers/       # REST 路由：resumes / jobs / applications
│   ├─ schemas/           # Pydantic models（與前端 TS 型別對應）
│   ├─ services/          # 業務邏輯，純函式好測
│   │   ├─ resume_diagnosis.py     # M2 履歷診斷
│   │   ├─ job_matching.py         # M4 契合度分析
│   │   ├─ cover_letter.py         # M5 求職信
│   │   └─ external_apply.py       # M6 外部投遞偵測
│   ├─ crawler/           # M4 Playwright 104 爬蟲
│   ├─ resume/            # M1 履歷解析（PDF/Word → text）
│   ├─ llm/               # Claude/OpenAI client 抽象層
│   ├─ db/                # MongoDB（motor async）+ repositories
│   └─ pipeline.py        # 串整條流程
├─ tests/
└─ pyproject.toml
```

**分層原則**：`api/` → `services/` → (`crawler/`、`resume/`、`llm/`、`db/`)。
上層依賴下層，下層不反向依賴 FastAPI。

---

## 4. Frontend 內部結構（`frontend/`）

```
frontend/
├─ src/
│   ├─ main.tsx
│   ├─ App.tsx            # 路由（React Router）
│   ├─ api/               # 打 backend 的 typed client
│   ├─ types/             # 對應 backend schemas 的 TS 型別
│   ├─ hooks/             # 資料抓取（TanStack Query）
│   ├─ pages/             # ResumeSetup / JobList / JobDetail / CoverLetter / Board
│   ├─ components/        # 共用元件
│   └─ theme.ts           # Mantine 主題
├─ package.json
└─ vite.config.ts
```

**頁面對應流程**：

| 頁面 | 對應流程 | 模組 |
|------|----------|------|
| ResumeSetup | 上傳履歷 + 設定目標職位/薪資 | M1 |
| JobList | 職缺清單 + 契合度排序 | M4 |
| JobDetail | 逐筆契合度分析、缺口 | M4 |
| CoverLetter | 求職信生成/編輯 | M5 |
| Board | 求職進度看板（後續） | P1 |

---

## 5. 前後端串接與本地開發

- **MongoDB**：`docker-compose.yml` 一鍵起本地 Mongo。
- **CORS**：FastAPI 開放 `localhost:5173`（Vite 預設 port）。
- **開發流程**：兩個終端，一個 `uv run uvicorn`、一個 `npm run dev`；
  Vite proxy 把 `/api` 轉到後端。
- **環境變數**：`backend/.env`（API keys、Mongo URI），已被 `.gitignore` 擋掉。

---

## 6. 測試策略

- **後端**：`pytest`，重點測 `services/`（純邏輯）；爬蟲與 LLM 用 mock。
- **前端**：MVP 先不強求，之後用 Vitest。

---

## 7. 不在本次範圍

- 各模組演算法細節（契合度維度、求職信語氣等）—— 見規劃文件待確認區。
- CI/CD、Zeabur/Cloudflare 部署設定 —— 第三週再處理。
- 多人使用、帳號與隱私 —— P2 之後。
