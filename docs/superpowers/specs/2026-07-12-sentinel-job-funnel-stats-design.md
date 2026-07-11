# career-sentinel 求職漏斗 / 進度統計儀表板 — 設計

**日期**：2026-07-12
**範圍**：`sentinel/` 子專案；新增功能（後端狀態事件 log + 統計聚合 + 前端統計頁）。

## 目標

用使用者現有的求職管道資料，提供一頁「求職統計」，把進度變成可看懂、可行動的數字：各階段人數漏斗、階段間轉換率、使用者可控階段的中位停留天數、以及停滯職缺提醒。

## 動機與資料現況

`TrackedJob` 只有 `created_at` / `updated_at`（最後一次變更），沒有狀態轉換歷史，因此無法算「在某階段停留幾天」。本設計新增一張輕量的狀態事件表補齊此能力。

管道狀態（`pipeline.STATE_RANK` + `TERMINAL`）：
`interested`(1) → `matched`(2) → `tailored`(3) → `applied`(4) → `interviewing`(5) → `offer`（終端·成功）；`rejected`（終端·失敗）。

其中 `interested/matched/tailored/offer/rejected` 是**使用者可控**、經 store 收斂點變更；`applied/interviewing` 是 **104 爬蟲衍生**（來自 applications / interviews，非狀態轉換事件）。

## 範圍決定（已與使用者確認）

- **停留天數**：只做**使用者可控的狀態**（interested/matched/tailored/offer/rejected），時間戳來自新的狀態事件 log，乾淨可靠。
- **applied / interviewing**：v1 只計入**漏斗人數與轉換率**，**不提供停留天數**（爬蟲時間戳關聯與自由字串解析脆弱，留待日後）。

## 架構

三層，皆遵循既有模式：

### ① 資料層：狀態事件 log（`store.py`）

- **新表 `state_events`**：欄位 `id INTEGER PK AUTOINCREMENT`、`code TEXT NOT NULL`、`state TEXT NOT NULL`、`at TEXT NOT NULL`（ISO 秒）。
- **寫入時機（只在真的換階段時）**：
  - `merge_tracked_job`：計算出 `final_state` 後，若 `existing is None`（首次）或 `final_state != existing.state`，append 一筆 `(code, final_state, now)`。（狀態沒變＝scrape 沿用寫入時**不記**，避免洗版。）
  - `set_tracked_state`：若 `existing is None` 或 `state != existing.state`，append 一筆 `(code, state, now)`。
  - 新增函式 `append_state_event(conn, code, state, at)` 與 `load_state_events(conn) -> list[StateEvent]`（依 `at, id` 排序）。
- **Migration / backfill**：建表後，對每個既有 `tracked_jobs` 且 `state_events` 尚無該 code 事件者，插入一筆合成事件 `(code, 現 state, created_at 或 updated_at)`，讓既有資料不空白。此 backfill 在 `connect()` 的 migration 區塊執行一次（冪等：以「該 code 尚無事件」為條件）。
- **`delete_tracked_job`**：一併刪除該 code 的 `state_events`（避免孤兒事件污染統計）。
- 新 model `class StateEvent(BaseModel): code: str; state: str; at: str`（`models.py`）。

### ② 聚合層：`stats.py`（新檔，可單測、不需網路）

`compute_stats(conn) -> StatsResult`（Pydantic model），內容：

- **funnel**: `list[FunnelStage]`，每項 `{state, label, count}`，順序固定為 interested→matched→tailored→applied→interviewing→offer。count 用**累積達到** `reached(state)`（定義見下方 conversions），故人數單調遞減、呈真正的漏斗形。資料來源為 `pipeline.build_pipeline(conn)` 的合併後 state。`rejected` 不進漏斗，另計於 `rejected_count`。
- **conversions**: `{applied_to_interview, interview_to_offer, interested_to_offer}`，各為 0–100 整數百分比，分母為 0 時回 `None`（前端顯示「—」）。
  - 以「**達到階段數** `reached(X)`」為基礎。`reached(X)` = 目前 pipeline 合併後 state 的 rank ≥ rank(X) 的 job 數，其中 rank 用 `STATE_RANK` 且 `offer` 視為 6（高於 interviewing 的 5）。
  - **`rejected` 排除在所有 `reached()` 計數之外**（現狀態下無法回溯其曾達到的最高階段，強行納入會失真）；`rejected` 只呈現在漏斗的 `rejected_count`。
  - 定義：
    - `applied_to_interview` = `reached(interviewing)` ÷ `reached(applied)`
    - `interview_to_offer` = `reached(offer)` ÷ `reached(interviewing)`
    - `interested_to_offer` = `reached(offer)` ÷ `reached(interested)`（分母即所有非 rejected 的追蹤職缺）
  - 判定資料來源：`pipeline.build_pipeline` 的合併後 state（反映爬蟲衍生的 applied/interviewing）。此為「仍在進行或已成功者的階段轉換率」，語意在前端以副標點明。
- **dwell**: `list[DwellStat]`，每項 `{state, label, median_days, sample}`，僅含 interested/matched/tailored/offer/rejected。由 `load_state_events` 依 code 分組、排成時間軸，每段停留 = 下一事件時間 − 本事件時間（現階段＝now − 本事件時間）；跨 code 收集同 state 的所有停留樣本取中位數（無條件捨去為整數天）。`sample` 為樣本數；樣本 0 時該項 `median_days=None`。
- **stale**: `list[StaleJob]`，每項 `{code, company, title, state, days_since_update, url}`，條件 `days_since_update > STALE_DAYS`（常數，預設 14），排除終端狀態（offer/rejected），依 `days_since_update` 由大到小排序。天數由 `updated_at` 對 now 計。

所有時間解析以 `datetime.fromisoformat`；壞資料以 try/except 跳過該筆（best-effort，不讓單筆髒資料炸整頁）。

### ③ API 層

- 於 `web/routers/dashboard.py` 新增 `@router.get("/api/stats")`，注入 `db_path`，回 `stats.compute_stats(store.connect(db_path)).model_dump()`。唯讀。

### ④ 前端：「求職統計」頁

- `web/frontend/src/StatsPage.tsx`（新）；`api.ts` 加 `getStats()` 型別與呼叫；`Sidebar.tsx` 新增 nav 項「求職統計」（放「儀表板」附近）、`App.tsx` 掛載、`PageKey` 增 `"stats"`。
- **漏斗**：各階段一列水平長條（寬度 ∝ count／最大 count），標籤含中文名 + 人數 +（佔總追蹤）%。純 CSS（Mantine `Box`/`Progress` 或 div），**不引入圖表套件**，配 Cockpit 深色主題。
- **轉換率**：三塊卡（投遞→面試、面試→offer、有興趣→offer），百分比大字；`None` 顯示「—」。
- **停留天數**：各階段中位天數水平長條（僅可控狀態），樣本 0 顯示「尚無資料」。
- **停滯提醒**：清單，每列「公司 · 職稱 · 現狀態 · X 天未更新 · 去 104 看」；空清單顯示鼓勵字。
- 載入中 `Loader`、錯誤 `Alert`。資料少（全空管道）時各區塊顯示友善占位字。

## 資料流

前端 `StatsPage` → `GET /api/stats` → `dashboard.router` → `stats.compute_stats(conn)` → 讀 `pipeline.build_pipeline`（漏斗/轉換）+ `store.load_state_events`（停留）+ `store.load_tracked_jobs`（停滯）→ 回 JSON → 前端渲染。

## 錯誤處理

- 後端：時間解析與 JSON 壞值以 try/except 跳過單筆；`compute_stats` 對空資料回全 0／空清單（不拋錯）。
- 前端：query 錯誤顯示 `Alert`；各區塊獨立處理空資料。

## 測試

- `tests/test_stats.py`（pytest，`store.connect(tmp)` + 種資料）：
  - 漏斗計數（多狀態 job 分組正確）。
  - 轉換率算式（含分母為 0 → None）。
  - 中位停留（塞多筆 `state_events` 時間軸，驗證中位天數與樣本數；現階段用 now 計）。
  - 停滯門檻（> 14 天入列、終端狀態排除、排序）。
- `tests/test_tracked_jobs_store.py` 增補：`merge_tracked_job`/`set_tracked_state` 換狀態才記事件、狀態不變不記；`delete_tracked_job` 連帶刪事件；backfill 冪等。
- 前端：`npm run build` 型別/建置通過。

## 非目標（YAGNI）

- 不做 applied/interviewing 的停留天數（v1 範圍外）。
- 不引入前端圖表套件（純 CSS 長條）。
- 不做時間區間篩選、匯出、歷史趨勢圖（日後可加）。
- 不改既有管道頁或儀表板既有區塊。
- `STALE_DAYS` 以常數提供，不做設定 UI。
