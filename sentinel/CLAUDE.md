# CLAUDE.md — career-sentinel（本機自架版）

給在此子專案工作的 AI agent 的導覽。**地端、單人、自帶 key** 的 104 求職助手：
讀你自己的 104 登入態 → 存本機 SQLite 快照 → diff 變化 → LLM 每日彙整 + 「求職總指揮」聊天 agent。

> 這是 `career_agent` monorepo 的 `sentinel/` 子專案，和線上多人版（`backend/` + `frontend/`）**完全獨立**。
> 改這裡不影響線上版，也不觸發線上部署。

## 硬限制（務必遵守）

- **agent 絕不寫入 104**：只讀取（誰看過我／投遞／訊息／面試、公開職缺 JD）。投遞頁只「開啟」讓使用者自己送，不代填不代送。
- **後端只綁 `127.0.0.1:8765`**（`cli.py`）。不要改成 `0.0.0.0` 或對外開放。
- **PII 不送 LLM**：履歷區塊 `is_pii=True`（如個人基本資料）不進 prompt，見 `scraper/resume104.py`。新增送 LLM 的路徑時要沿用此過濾。
- **讀 104 私人頁必須 headful**：`browser.py` 用 rebrowser-playwright `headless=False` 過 Cloudflare/DataDome。不要改 headless。
- **不要 `taskkill` 全部 `chrome.exe`**：只關專案 profile 的 Chrome（`data/chrome-profile`），否則會關掉使用者自己的瀏覽器。
- 公開職缺／JD 走 `curl_cffi`（`impersonate="chrome"` 模擬 TLS 指紋），不需登入、不需開瀏覽器。

## 常用指令

```bash
# 測試（一定用專案 venv，不要用系統 python）
./.venv/Scripts/python.exe -m pytest -q      # 或：uv run pytest

# 前端（改 web/frontend 後要重建；serve 提供 dist）
cd web/frontend && npm run build

# 執行
uv run career-sentinel login    # 首次：開專用 Chrome 手動登入 104（只存 profile、不存帳密）
uv run career-sentinel serve    # 起 web → http://127.0.0.1:8765
uv run career-sentinel run      # 只跑一次「擷取 → 比對 → 彙整」（不開 web）
```

改完程式的驗收基準：`pytest -q` 全綠 + `npm run build` 通過。

## LLM provider（`config.py`）

偵測順序（presence-based）：有 `FOUNDRY_API_KEY` → **foundry**；否則有 `LLM_API_KEY` → **openai 相容**；否則空。

- **foundry**（目前實際可用）：Azure AI Foundry 的 Anthropic 端點。`FOUNDRY_API_KEY` / `FOUNDRY_BASE_URL`（`https://<資源>.services.ai.azure.com/anthropic`）/ `FOUNDRY_MODEL`（`claude-sonnet-4-6`）。**只有 foundry 有原生 tool-use 聊天編排**（`chat.stream_with_tools`）。
- **openai 相容**：`LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`。
- `SENTINEL_DATA_DIR` 可覆寫資料目錄（預設 `sentinel/data`）。

## 架構地圖

```
src/career_sentinel/
├─ cli.py            login / run / serve 進入點；run_pipeline（擷取→diff→彙整，失敗沿用上次）
├─ browser.py        rebrowser headful context（過 Cloudflare）— 改動需驗證仍能登入
├─ scraper/          讀 104，每個資料源一檔：viewers/applications/messages/interviews/recommend/search/resume104
│                    real.py=真爬蟲組裝、fake.py=測試假資料（可抽換）
├─ store.py          SQLite：快照、tracked_jobs（含 offer_json/interviews_json）、settings、chat、memory
├─ models.py         全部 Pydantic v2 model（Snapshot/TrackedJob/PipelineJob/RecommendedJob/...）
├─ diff.py/digest.py 跟上次比對變化 + LLM 每日彙整
├─ pipeline.py       求職管道狀態機（interested→matched→tailored→applied→interviewing→offer/rejected）
├─ match/tailor/negotiate/research/diagnosis.py   各自獨立的 LLM 任務（單一職責）
├─ chat.py           求職總指揮：prompt 組裝 + tool 定義/執行 + tool-use 迴圈 + 確認卡 + compact/記憶
├─ llm.py            LLM 抽象（parse_json / chat_stream / _with_today）
├─ jobfetch.py       curl_cffi 抓 104 公開職缺/JD
├─ config.py         env / 路徑 / provider 偵測
└─ web/
   ├─ app.py         FastAPI create_app（所有 /api 路由）
   ├─ runner.py      背景擷取工作 + 瀏覽器忙碌鎖（try_begin_browser）
   ├─ scheduler.py   每日提醒排程
   └─ apply.py       開 104 投遞頁（只開，不寫入）

web/frontend/src/    React + Vite + TS + Mantine（Cockpit 深色主題）
├─ Dashboard.tsx / FindJobsPage.tsx / ChatPage.tsx（求職總指揮）/ ProfilePage.tsx / AboutPage.tsx
├─ JobCardDrawer.tsx（含面試紀錄）/ JobRow.tsx（compact 供聊天窄面板）
└─ api.ts            所有後端呼叫集中在此
```

## 聊天 agent（`chat.py`）重點

- **確認卡機制**：會動到資料或花 LLM 費用的動作，agent 輸出 `<suggestions>` → 前端渲染確認卡 → 使用者按下才 `apply_update` 生效。讀取型工具（search_jobs / get_pipeline / get_job_detail / fetch_url）自動執行。
- `TOOLS` 是給 LLM 的工具 schema；`_execute_tool` 分派；`stream_with_tools` 跑 tool-use 迴圈（上限 `TOOL_LOOP_MAX`）。
- 新增聊天工具：加進 `TOOLS`、在 `_execute_tool` 分派、更新系統提示（`build_system_prompt`）說明用途。
- `search_jobs` 支援 `page`；前端搜尋結果面板另有「載入更多」直接翻頁（不靠 agent 記憶）。
- `interviews_json` / `offer_json` 這類欄位在 `store.merge_tracked_job` 與 `set_tracked_state` 的既有分支**必須沿用帶回**，否則下次擷取或改狀態會被清空（曾發生過的 bug 類型）。

## 慣例

- 日常開發在 `dev`，驗證 OK 才 `git checkout main && git merge --ff-only dev` 再 push。
- `git add` 從 repo 根目錄用完整路徑（`sentinel/...`），避免 cwd 卡在子目錄導致 pathspec 失敗。
- 資料在 `data/`（SQLite + chrome-profile），gitignored。
