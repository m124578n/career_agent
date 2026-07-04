# career-sentinel SP14：等待處可見進度流程 設計

> 日期：2026-07-04。狀態：使用者已核可設計，直接進 plan → subagent 開發。
> 前情：SP1–SP13 完成、252 測試。剛修掉「切分頁清空 local state」（全分頁 keepMounted）。

## 目標

在需要等待的地方顯示進度給使用者看：
- **爬蟲**（`/api/scrape` 背景管線）：真階段 stepper（全域、切分頁也看得到）。
- **LLM 單次呼叫＋同步爬蟲**（健檢/比對/客製化/研究/104健檢/推薦/搜尋/開投遞頁）：inline「進行中…（已 N 秒）」計時（無真子步驟、不假造）。

## 使用者決策（已定）

- 流程＝**真實階段步驟**（爬蟲真報階段；LLM 單次用計時、不做假步驟）。
- 位置＝**全域條 + 分頁內**（爬蟲全域 stepper；LLM/同步爬蟲各分頁內就地計時）。

## Part A — 爬蟲階段 stepper（全域、真階段）

### 後端

`web/runner.py`：
- `_State` 加 `phase: str = ""`。
- `status()` 輸出 `"phase": _state.phase`。
- 新 `set_phase(name: str)`：`with _lock: _state.phase = name`（best-effort、供 scrape 回報）。
- `_run`：進 `try` 前不特別設；`finally` 內 `end_browser()` 之後 `set_phase("")`（結束/失敗都清空）。
- `default_scrape`：
  - 開始時 `set_phase("establish")`。
  - 傳 `on_phase=set_phase` 給 `real.scrape_session`。
  - `real.scrape_session` 回來後（進 `run_pipeline` 前）`set_phase("digest")`。
  - 正常結束不需在此清（由 `_run` 的 finally 清）。

`scraper/real.py`：
- `scrape(page, on_phase=None)`：每個 reader 迴圈**前** `on_phase and on_phase(name)`（name = viewers/applications/messages/interviews）。
- `scrape_session(on_phase=None)`：`establish_session` 成功後、`scrape(page)` 前不用再報（establish 由 default_scrape 先報）；把 `on_phase` 傳給 `scrape(page, on_phase=on_phase)`。
- **best-effort**：`on_phase` 呼叫本身不包 try（callback 端 `set_phase` 自身簡單不拋）；但 `on_phase` 為 None 時完全不呼叫。reader 失敗（現有 try/except）不影響後續 reader 的 phase 回報。

階段值（後端回報的 `phase` 字串）：`establish` / `viewers` / `applications` / `messages` / `interviews` / `digest` / `""`(閒置)。

### 前端

`api.ts`：`StatusResp` 加 `phase: string`（`getStatus` 已存在、免改）。

`App.tsx`：
- 在 `AppShell.Main` 內、`due` 橫幅與頁內容之上，`running` 時渲染 `<ScrapeStepper phase={status.data?.phase ?? ""} />`（全域、任何分頁可見）。
- 沿用既有 `status` 每 2s 輪詢（`refetchInterval: polling ? 2000 : false`）。

新 `ScrapeStepper.tsx`：
- 六段固定順序＋中文標籤：
  `[{key:"establish",label:"建立連線"},{key:"viewers",label:"誰看過我"},{key:"applications",label:"應徵"},{key:"messages",label:"訊息"},{key:"interviews",label:"面試"},{key:"digest",label:"整理"}]`
- 用 Mantine `Stepper`（或水平 `Group` 自繪）：目前 phase 對應 index 高亮、前面的打勾；phase 空或不在清單→不顯示（元件只在 `running && phase` 時有內容，App 已 gate `running`）。
- Cockpit 深色主題、小尺寸、放在內容頂部一條。

## Part B — 單次等待 inline 計時

純前端，無後端。

- 新 `useElapsed.ts`：`useElapsed(active: boolean): number`——`active` 為真時每 1 秒 +1，轉 false 歸零。用 `useEffect` + `setInterval`，cleanup 清 interval。
- 新 `BusyHint.tsx`：`<BusyHint active label />`——`active` 時顯示 `<Loader size="xs"/>` ＋ `Text`「{label}…（已 {useElapsed(active)} 秒）」；否則 null。小字、次要色。
- 套用各頁等待處（把該頁既有的 busy 布林傳入、label 中文）：
  - `ResumePage`：健檢 busy → label「分析中」。
  - `MatchPage`：比對 busy → 「比對中」。
  - `TailorPage`：客製化 busy → 「產生中」；開投遞頁 applyBusy → 「開啟中」。
  - `RecommendPage`：拉取 busy → 「抓取中」；逐列比對各自的 busy → 「比對中」。
  - `SearchPage`：搜尋 busy → 「搜尋中」。
  - `Resume104Page`：讀取 busy →「讀取中」；健檢 busy →「分析中」。
  - `CompanyResearch`（若在 Dashboard/研究按鈕）：研究 busy →「研究中」。
- 放在觸發按鈕旁或下方；不取代既有的錯誤顯示。

## 邊界與安全

- 爬蟲 phase best-effort：回報只是寫字串、失敗不影響抓取；`_run` finally 一律清空 phase（避免殘留）。
- recommend/resume104/apply 等**同步阻塞**爬蟲不進全域 stepper（無子步驟）——走 Part B inline 計時。
- 不做（YAGNI）：LLM 假步驟、每 reader 內部 %、爬蟲取消鈕、跨裝置、歷史耗時統計。

## 測試

- `test_runner`：`set_phase` 更新 `_state.phase`、`status()["phase"]` 反映、`_run` 結束後 phase 歸空（成功與例外路徑各一）。
- `test_real_scrape`（或既有 scrape 測試擴充）：`scrape(page, on_phase=collector)` 依序收到 `["viewers","applications","messages","interviews"]`；`on_phase=None` 不炸；某 reader 丟例外時後續 reader 仍被回報（phase 序列完整）。
- 前端 build 零 TS 錯誤。
- 真機：重新抓取 → 頂部 stepper 隨階段前進、切分頁仍可見；跑健檢/比對/搜尋 → 按鈕旁「…（已 N 秒）」計時。
