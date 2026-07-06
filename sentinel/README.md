# career-sentinel — 104 地端哨兵

**地端、單人、自帶 key** 的求職助手。在你自己的電腦上跑，用你自己的瀏覽器登入態讀 104
（誰看過我 / 投遞狀態 / 訊息 / 面試邀約），存成本機 SQLite 快照、跟上次比對變化、用 LLM
每日彙整，並提供一個「求職總指揮」聊天 agent，讓你**跟 agent 聊天就把整條求職流程做完**。

> 這是 `career_agent` monorepo 的本機自架版本。雲端多人版（Google 登入即用）見
> [根目錄 README](../README.md)。

## 它能做什麼

- **儀表板**：誰看過我、投遞狀態、訊息、面試邀約，跟上次擷取比對出變化、LLM 產生每日彙整；
  即將到來的面試附「加入 Google 日曆」連結。
- **求職總指揮（聊天 agent）**：跟 agent 對話即可
  - 整理履歷與求職偏好（目標職稱、期望薪資、地點、軟條件、避雷）
  - 搜尋 104 職缺、讀 JD、逐筆比對契合度
  - 生成客製化履歷建議與求職信、開 104 投遞頁（agent **不代你投遞、不寫入 104**）
  - 追蹤求職管道（追蹤 / 標記錄取 offer / 未錄取 / 重設）
  - offer 明細記錄、並排比較、依市場行情給議價策略與話術
  - **面試紀錄**：為每個職缺記錄面試時間與內容（卡片手動記，或請 agent 記）
  - 讀取型工具（search_jobs / get_pipeline / get_job_detail / fetch_url）自動執行；
    會動到資料或花 LLM 費用的動作走「確認卡」，按下才生效
- **履歷**：上傳 PDF、或從 104 線上履歷匯入；對著目標職缺做健檢診斷。
- **隱私**：全程本機執行、資料留在你電腦；讀 104 用專用 Chrome profile 的登入態（**不存帳密**）；
  後端只綁 `127.0.0.1`。

## 需求

- Python 3.12 以上
- [uv](https://docs.astral.sh/uv/)（Python 套件/環境管理器）與 Git
- 一個 104 帳號
- 一組 LLM key（目前實際可用：**Azure AI Foundry 的 Claude Sonnet**）

## 安裝

```bash
cd sentinel
uv sync
uv run rebrowser_playwright install chromium   # 裝 patch 過的反偵測瀏覽器驅動
```

## 設定 LLM key（`.env`）

```bash
cp .env.example .env
```

目前實際可用的是 **Azure AI Foundry 上的 Claude Sonnet**，`.env` 填：

```dotenv
FOUNDRY_API_KEY=你的-Foundry-Key
FOUNDRY_BASE_URL=https://<你的資源名>.services.ai.azure.com/anthropic
FOUNDRY_MODEL=claude-sonnet-4-6
```

> 申請步驟（部署 Claude Sonnet、拿 Target URI + Key）見線上版網站的 **「本機自架」頁（`/self-host`）**。
> Base URL 是 Foundry Details 頁的 Target URI 去掉結尾的 `/v1/messages`。

也支援任何 **OpenAI 相容端點**（設 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`）。偵測順序：
有 `FOUNDRY_API_KEY` → 走 Foundry；否則有 `LLM_API_KEY` → 走 OpenAI 相容。

| 變數 | 說明 |
|------|------|
| `FOUNDRY_API_KEY` / `FOUNDRY_BASE_URL` / `FOUNDRY_MODEL` | Azure AI Foundry（Anthropic）路徑 |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | OpenAI 相容端點路徑 |
| `SENTINEL_DATA_DIR` | 選填，覆寫資料目錄（預設 `sentinel/data`） |

## 使用

```bash
uv run career-sentinel login    # 首次：開專用 Chrome 手動登入 104（只存 profile、不存帳密）
uv run career-sentinel serve    # 起本地 web：儀表板 + 求職總指揮 → http://127.0.0.1:8765
uv run career-sentinel run      # 或：只跑一次「擷取 → 比對 → 彙整」（不開 web）
```

啟動 `serve` 後用瀏覽器開 [http://127.0.0.1:8765](http://127.0.0.1:8765)。

> 104 私人頁在 Cloudflare 後面，首次或偶爾可能要在開啟的瀏覽器過一次人機驗證。

## 架構

```
sentinel/
├─ src/career_sentinel/
│  ├─ cli.py            # login / run / serve 進入點
│  ├─ browser.py        # rebrowser-playwright headful context（反偵測、過 Cloudflare）
│  ├─ scraper/          # 讀 104（誰看過我/投遞/訊息/面試、線上履歷）
│  ├─ store.py          # SQLite 快照、追蹤職缺、offer、面試紀錄
│  ├─ diff.py / digest.py   # 跟上次比對變化 + LLM 每日彙整
│  ├─ pipeline.py       # 求職管道（追蹤 → 比對 → 客製化 → offer）狀態機
│  ├─ match.py / tailor.py / negotiate.py / research.py / diagnosis.py  # LLM 任務
│  ├─ chat.py           # 求職總指揮：tool-use 迴圈 + 確認卡 + 記憶
│  ├─ llm.py            # LLM provider 抽象（Foundry / OpenAI 相容）
│  ├─ jobfetch.py       # curl_cffi 抓 104 公開職缺/JD（Chrome TLS 指紋）
│  └─ web/app.py        # FastAPI（綁 127.0.0.1，serve 儀表板 + API）
├─ web/frontend/        # React + Vite + TS + Mantine（Cockpit 深色主題）儀表板/聊天 UI
├─ tests/               # pytest
└─ data/               # SQLite + Chrome profile（gitignored）
```

**技術重點**
- **rebrowser-playwright**：playwright 的 drop-in 替換，打了反偵測 patch（修 CDP `Runtime.enable`
  洩漏），headful 讀 104 登入態並自動通過 Cloudflare/DataDome challenge。
- **curl_cffi**：模擬 Chrome TLS 指紋抓 104 公開職缺/JD（避開 WAF 的 JA3 封鎖），不需開瀏覽器。
- **本機優先**：SQLite + 本機 Chrome profile；後端只綁 `127.0.0.1`；PII 區塊（`is_pii`）不送 LLM。

## 開發

```bash
# 後端測試（用專案 venv）
uv run pytest

# 前端（改儀表板/聊天 UI 後重建；serve 提供 dist）
cd web/frontend && npm install && npm run build
```

## 授權/免責

僅供個人求職使用；讀取的是**你自己的** 104 登入態資料。agent 只讀取、不代你投遞或寫入 104。
