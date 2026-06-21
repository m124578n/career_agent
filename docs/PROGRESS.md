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

## 🔲 待辦（backlog）

- **前端**：職缺頁串 `/api/jobs`（列表 + crawl 觸發 + 契合度能量條）；求職信頁
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
