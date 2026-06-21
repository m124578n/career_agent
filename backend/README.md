# job-tracker（backend）

104 Job Tracker 後端，FastAPI + MongoDB + Playwright + Claude。

## 開發

```bash
# 安裝相依
uv sync

# 安裝 Playwright 瀏覽器（爬蟲用）
uv run playwright install chromium

# 複製環境變數
cp .env.example .env   # 填入 ANTHROPIC_API_KEY 等

# 起本地 MongoDB（在 repo 根目錄）
docker compose up -d

# 啟動 API（http://localhost:8000，文件 /docs）
uv run uvicorn job_tracker.main:app --reload
```

## 測試

```bash
uv run pytest
```

## 結構

- `api/routers/` — REST 路由
- `services/` — 業務邏輯（M2/M4/M5/M6），不依賴 FastAPI
- `crawler/` — Playwright 104 爬蟲（M4）
- `resume/` — 履歷解析（M1）
- `llm/` — Claude/OpenAI client 抽象
- `db/` — MongoDB 連線
- `pipeline.py` — 串整條流程
