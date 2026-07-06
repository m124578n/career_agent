# 線上版「本機自架」介紹＋教學頁 設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作
**目標 codebase：** 線上版 `frontend/`（React + react-router + Mantine，部署 Cloudflare Pages）——**非** `sentinel/`。

## 這是什麼

在線上版 JobTracker（`frontend/`）加一個**公開頁**，介紹本機自架版 **career-sentinel**，並附**完整詳細的啟動教學**（環境配置 → Azure AI Foundry Claude key 申請 → 啟動）。

## 現況（實作依據）

- **路由（`frontend/src/main.tsx`）**：頁面放 `frontend/src/pages/`、`lazy(() => import(...).then(m => ({default: m.Named})))`、`<Route path=... element={...}/>`。`/about`、`/`（RootRoute）在 `GatedShell` **之外＝公開**；`/home`/`/resume`/`/jobs`/`/applications` 在 `GatedShell` 內需登入。
- **Landing（`frontend/src/pages/Landing.tsx`）**：公開首頁，已有導向 `/about` 的連結（「關於作者 →」）。
- **頁面視覺慣例**：`jt-panel`/`jt-panel-body`/`jt-eyebrow`/`jt-brand` CSS class（見 `About.tsx`）；Mantine `Title`/`Text`/`Anchor`/`Stack`/`Group`/`Badge`；`Footer` 元件。
- **career-sentinel 實際啟動需求（來源 `sentinel/README.md`、`.env.example`、`config.py`、`pyproject.toml`）**：
  - 需求：Python 3.12+、`uv`、Git、104 帳號、Azure AI Foundry 的 Claude key。
  - 安裝：`cd sentinel` → `uv sync` → `uv run rebrowser_playwright install chromium`。
  - 設定：`cp .env.example .env`。**目前實際可用路徑＝Azure AI Foundry**，env：`FOUNDRY_API_KEY`、`FOUNDRY_BASE_URL`、`FOUNDRY_MODEL`（預設 `claude-sonnet-4-6`）。`config.llm_provider()`：有 `FOUNDRY_API_KEY`→foundry。
  - 啟動：`uv run career-sentinel login`（首次手動登 104）→ `uv run career-sentinel serve`（開 `http://127.0.0.1:8765`；儀表板＋求職總指揮）或 `run`（跑一次擷取）。
  - 註：`.env.example` 現寫 OpenRouter 預設（LLM_*），與實際可用的 Foundry 路徑不一致——**本頁照 Foundry 教**，不改 `.env.example`（另議）。

## 設計

### 頁面
- 新增 `frontend/src/pages/SelfHost.tsx`（named export `SelfHost`）。
- `main.tsx`：`const SelfHost = lazy(...)`；公開路由 `<Route path="/self-host" element={<SelfHost />} />`（放在 `/about` 那組公開路由旁、`GatedShell` 之外）。
- 視覺沿用 `About.tsx` 慣例（`jt-panel`/`jt-eyebrow`、Mantine、頂部 `JobTracker.` brand ＋「← 回首頁」、底部 `Footer`）。指令用 `<Code>` 或 `<pre className="...">` 區塊（等寬、可讀）。

### Landing 連結
- `Landing.tsx` 在既有 `/about` 連結附近加一個導向 `/self-host` 的連結/CTA（如「自己架一台哨兵 →」）。

### 內容區塊（繁中，完整詳細）
1. **介紹**：career-sentinel 是什麼——本機、單人、自帶 key、讀 104 登入態（誰看過我／投遞狀態／訊息／面試）、資料留本機、agent 不寫入/不代投遞 104；與線上 JobTracker 差異（自架 vs 雲端多人）；GitHub repo 連結（`https://github.com/m124578n/career_agent`）。
2. **需求**：Python 3.12+、`uv`、Git、104 帳號、Azure AI Foundry 的 Claude key。
3. **安裝**：`git clone` → `cd sentinel` → `uv sync` → `uv run rebrowser_playwright install chromium`（說明是 patch 過的反偵測瀏覽器驅動）。
4. **申請 Azure AI Foundry 的 Claude Sonnet key（詳細逐步）**：註冊/登入 Azure → 進 Azure AI Foundry → 部署 Claude Sonnet 模型 → 取得 endpoint、API key、部署名稱。**實作時 WebFetch 現行 Azure AI Foundry 文件確保步驟正確、用詞對得上現行 UI。**
5. **設定 `.env`**：`cp .env.example .env`；填 `FOUNDRY_API_KEY=`、`FOUNDRY_BASE_URL=`（Foundry endpoint）、`FOUNDRY_MODEL=claude-sonnet-4-6`；說明這是目前唯一實際可用路徑。
6. **登入 104**：`uv run career-sentinel login`（開專用 Chrome profile 手動登入，只存 profile、不存帳密）。
7. **啟動**：`uv run career-sentinel serve` → 瀏覽器開 `http://127.0.0.1:8765`（儀表板＋求職總指揮）；或 `uv run career-sentinel run` 跑一次擷取→比對→彙整。
8. **注意事項**：104 私人頁在 Cloudflare 後面（首次可能要過真人驗證）；資料存 `sentinel/data`（可用 `SENTINEL_DATA_DIR` 覆寫）；agent 只讀不代投遞。

### 性質
純靜態內容頁：無 API、無 state、無 auth。

## Global Constraints
- 目標 codebase＝`frontend/`（線上版），非 `sentinel/`。
- 公開頁（`GatedShell` 外），免登入可看。
- 視覺沿用 `frontend` 既有慣例（`jt-panel`/`jt-eyebrow`/Mantine/`Footer`），不引入新設計語言。
- key 教學**只涵蓋 Azure AI Foundry Claude Sonnet**（其他 provider 尚未可用，不教）。
- 教學指令與 env 變數必須與 `sentinel` 現況一致（`uv sync`、`rebrowser_playwright install chromium`、`FOUNDRY_*`、`career-sentinel login`/`serve`/`run`）。
- 驗證：`frontend/` 的 `npm run build` 必過；無單元測試（內容頁）。

## 明確不做（Out of Scope）
- 其他 LLM provider（OpenRouter/OpenAI/Anthropic…）的 key 教學。
- 改 `sentinel/.env.example` 的 OpenRouter/Foundry 不一致（另議）。
- 加入 gated 側欄 NAV（僅 Landing 公開連結）。
- backend（Zeabur）任何改動。
