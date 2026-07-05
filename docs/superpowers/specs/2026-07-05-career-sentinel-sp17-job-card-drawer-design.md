# SP17：職缺連動卡片（Drawer）設計

**日期：** 2026-07-05
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 求職流水線第三個子專案。SP15 鋪了職缺脊椎＋求職中心，SP16 做了找職缺合一＋追蹤。SP17 讓求職中心的職缺能**點開一張右側 Drawer 卡片**，把 `比對 / 研究 / 客製化` 串在同一個職缺脈絡上、結果快取、完成客製化自動 tag，並把獨立的「客製化」頁摺進卡片。

roadmap：SP15 ✅ → SP16 ✅ → **SP17（本篇）** → SP18 履歷合一＋偏好集中 → SP19 offer 比較 → SP20 聊天總指揮。

## 目標

一句話：**求職中心點開職缺 → 右側 Drawer 卡片把 比對/研究/客製化 串起來、結果每職缺快取、完成客製化自動 tag `已客製化`。**

## 現況（實作依據）

- **`POST /api/match`**（收 `{job_url}`）→ `{title, company, salary, score, reasons, gaps}`。目前純計算、不持久化。
- **`POST /api/tailor`**（收 `{job_url}`）→ `TailoredApplication`（`job_title/company/resume_tips/resume_adjustments/missing_keywords/cover_letter`）。純計算、不持久化。
- **`POST /api/apply/open`**（收 `{job_url}`）→ 用登入態 Chrome 開職缺頁（客製化頁的「開啟投遞頁」）。
- **`GET /api/research?company=`**（既有）→ `CompanyResearch`，已快取於 `company_research` 表；前端 `ResearchButton` 是一個開 Modal 的按鈕。
- **`tracked_jobs`（SP15/16）**：`code`(PK)/company/title/url/salary/state/match_score/created_at/updated_at；store 有 `get_tracked_job`/`upsert_tracked_job`/`load_tracked_jobs`/`delete_tracked_job`。
- **`POST /api/tracked`（SP16）**：收 `_TrackReq`，upsert（去重、取較前面狀態、不降級終端 offer/rejected、保留 created_at）。
- **求職中心（`Dashboard.tsx`）**：職缺管道各群組的列（`Row`）目前點列無展開行為。
- **`FindJobsPage`/`ChatPage`**：各自宣告 `TRACKED_STATES`/`trackedCodes`（重複，SP16 留的 backlog）；trackedCodes 由 `/api/snapshot` pipeline 內 state 過濾（SP16 留的 backlog：同時被 104 判 applied/interviewing 的手動追蹤職缺會被漏判）。
- **`TailorPage.tsx`**：獨立頁，貼網址→tips/調整/關鍵字/求職信＋複製＋開啟投遞頁；導覽 `tailor` 項。

## 資料模型

### `tracked_jobs` 加兩欄（存卡片快取）

```sql
ALTER：tracked_jobs 新增
    match_json TEXT NOT NULL DEFAULT '',
    tailor_json TEXT NOT NULL DEFAULT ''
```

- 用加法式遷移：在 `_SCHEMA` 的 `CREATE TABLE tracked_jobs` 定義直接含這兩欄（新 DB 建表即有）；**既有 DB** 需一次性 `ALTER TABLE ... ADD COLUMN`（見下相容策略）。
- `match_json`：`POST /api/match` 結果的完整 JSON 字串（`{title,company,salary,score,reasons,gaps}`），`''` = 尚無。
- `tailor_json`：`TailoredApplication` 的完整 JSON 字串，`''` = 尚無。
- 研究結果不進此欄（已在 `company_research` 依公司快取）。

**相容策略（既有 DB 遷移）**：`store.connect()` 目前只跑 `CREATE TABLE IF NOT EXISTS`，不會替既有表加欄。SP17 在 `connect()` 內（executescript 之後）加一段冪等的 `ALTER TABLE tracked_jobs ADD COLUMN`，用 `PRAGMA table_info` 檢查欄位是否已存在再決定加不加（不存在才加），確保既有 DB 升級不炸、且重複啟動安全。

### `TrackedJob` model 加兩欄

```python
class TrackedJob(BaseModel):
    ...既有...
    match_json: str = ""
    tailor_json: str = ""
```

`store.load_tracked_jobs`/`get_tracked_job`/`upsert_tracked_job` 的 SELECT/INSERT 補上這兩欄。

## 後端變更

### 1. `POST /api/tracked` 擴充存 JSON（`web/app.py`）

`_TrackReq` 加兩個選填欄位：

```python
class _TrackReq(BaseModel):
    ...既有 code/company/title/url/salary/match_score...
    match_json: dict | None = None
    tailor_json: dict | None = None
```

端點 upsert 邏輯延伸（沿用既有「取較前面、不降級終端、保留 created_at」）：
- `match_json` 有值 → 存 `json.dumps(match_json, ensure_ascii=False)`，且視為 `matched`（同 match_score 情境）。
- `tailor_json` 有值 → 存 `json.dumps(tailor_json, ensure_ascii=False)`，且視為 `tailored`（新狀態候選，rank=3）。
- 兩個 json 未帶時保留既有值（不清空）。
- state 決策：`new_state` = `tailored`（若帶 tailor_json）> `matched`（若帶 match_score/match_json）> `interested`（皆無）；再與既有 state 取較前面、不降級終端。

> 為 DRY，把「合併 upsert」邏輯抽成 `store.merge_tracked_job(conn, code, *, state=None, match_score=None, match_json=None, tailor_json=None, company="", title="", url="", salary="") -> str`（回最終 state），SP16 的 `POST /api/tracked` handler 與本次一起改用它。此 helper 封裝：get_tracked_job → 保留 created_at → 取較前面/不降級終端 → 未帶欄位保留舊值 → upsert。

### 2. 新 `GET /api/tracked/{code}`（讀快取，卡片開啟用）

回該職缺的快取（不存在時回空殼、非 404，方便前端）：

```python
@app.get("/api/tracked/{code}")
def tracked_get(code: str) -> dict:
    tj = store.get_tracked_job(_conn(), code)
    if tj is None:
        return {"code": code, "found": False, "state": "", "match_score": None,
                "match": None, "tailor": None}
    return {
        "code": tj.code, "found": True, "state": tj.state, "match_score": tj.match_score,
        "match": json.loads(tj.match_json) if tj.match_json else None,
        "tailor": json.loads(tj.tailor_json) if tj.tailor_json else None,
    }
```

### 3. `/api/snapshot` 輸出 `tracked_codes`（SP16 backlog）

`_snapshot_payload` 新增 `"tracked_codes": [tj.code for tj in store.load_tracked_jobs(conn)]`（best-effort，包 try/except，失敗回 `[]`）。讓前端「已追蹤」判定基於真實 tracked_jobs 而非 pipeline effective state。

## 前端變更

### 4. 共用 `TRACKED_STATES` / trackedCodes（SP16 backlog）

- 前端不再用 pipeline state 過濾判已追蹤，改用 `/api/snapshot` 的 `tracked_codes`。
- `FindJobsPage`/`ChatPage` 的 `const trackedCodes = new Set(snap.data?.tracked_codes ?? [])`，移除各自的 `TRACKED_STATES` 宣告（消重）。`SnapshotResp` 型別加 `tracked_codes: string[]`。

### 5. `JobCardDrawer.tsx`（新，右側 Drawer）

- Props：`opened: boolean`、`onClose: () => void`、`job: { code; company; title; url; ... } | null`（由求職中心點的那筆帶入）。
- 開啟時 `GET /api/tracked/{code}` 取快取，prefill `比對`與`客製化`結果（有就直接顯示，不重跑）。
- 三區：
  - **比對**：有 `url` 才顯示按鈕。按下 → `POST /api/match {job_url: url}` → 拿結果後 `POST /api/tracked {code, company, title, url, salary, match_score: score, match_json: <結果>}` 快取＋auto-tag matched → invalidate `snapshot` 與本卡片快取。顯示分數/理由/缺口。
  - **研究**：一律可用，嵌入既有 `<ResearchButton company={job.company} />`（沿用其 Modal 與快取，不重造）。
  - **客製化**：有 `url` 才顯示按鈕。按下 → `POST /api/tailor {job_url: url}` → 拿結果後 `POST /api/tracked {code, ..., tailor_json: <結果>}` 快取＋auto-tag tailored → invalidate。顯示 tips/調整/關鍵字/求職信＋`複製求職信` ActionIcon ＋ `開啟投遞頁`（`POST /api/apply/open {job_url: url}`）。無 `url` 時該區顯示「此職缺無可用網址，無法客製化」。
- 視覺沿用 Cockpit 主題與既有 `Paper bg="dark.6"` 卡片樣式；文案沿用 TailorPage 既有用語。

### 6. 求職中心列可點開卡片（`Dashboard.tsx`）

- 職缺管道各群組的列（面試中/已投遞/已客製化/已比對/有興趣）點擊 → 開 `JobCardDrawer` 帶入該筆（code/company/title/url〔取 `job_url` 或 tracked url〕/salary）。既有的 gcal/知道了-還原/取消追蹤等列內 ActionIcon 用 `stopPropagation` 避免點按鈕誤開卡片。
- Drawer 開關狀態與「目前選的職缺」由 `Dashboard` 管理。

### 7. 移除 `TailorPage` 與導覽項

- 刪 `sentinel/web/frontend/src/TailorPage.tsx`。
- `Sidebar.tsx`：`PageKey` 移除 `"tailor"`；`NAV` 移除客製化項（`IconWand` 若不再用一併移除 import）。
- `App.tsx`：移除 `TailorPage` import 與其 `<div>`。

## Global Constraints（實作時必守）

- **不改動 `POST /api/match`、`POST /api/tailor` 的行為與回傳**：卡片是在前端拿到結果後另呼叫 `POST /api/tracked` 快取，**不讓 FindJobsPage 的 inline 比對變成自動追蹤**（SP16 的「比對≠追蹤」不變）。
- **快取/auto-tag 是純本地寫入，不碰 104**：只 `POST /api/tracked`（本地 SQLite）。研究沿用既有 `company_research` 快取。
- **加法式遷移不炸既有 DB**：`tracked_jobs` 兩新欄用 `PRAGMA table_info` 檢查後冪等 `ALTER TABLE ADD COLUMN`；新 DB 由 `_SCHEMA` 直接含欄。
- **auto-tag 不降級**：客製化→tailored、比對→matched，經 `merge_tracked_job` 與既有 state 取較前面、不覆蓋既有終端 offer/rejected。對 104 已投遞/面試中職缺操作只寫 tracked_jobs，effective 狀態仍由 104 訊號主導（pipeline 不變）。
- **不得弄丟 SP7 面試功能與 SP15/16 既有管道**：Dashboard 只加「列可點開 Drawer」，既有列內按鈕（gcal/dismiss-restore/取消追蹤/研究）行為不變、且用 `stopPropagation` 不誤觸卡片。
- **相容**：`/api/snapshot` 只新增 `tracked_codes`；`/api/tracked`（POST）擴充為向後相容（新欄選填）；search/recommend/match/tailor/apply 端點回傳不變。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 `127.0.0.1`；前端 `npm run build`（noUnusedLocals）必過。

## 測試策略

- **store**：`merge_tracked_job` — 新增/合併（保留 created_at、取較前面、不降級終端、未帶欄位保留舊值、match_json/tailor_json 存取 round-trip）；`tracked_jobs` 兩新欄 round-trip；既有 DB（缺兩欄的舊 schema）經 `connect()` 後長出新欄（模擬遷移）。
- **`POST /api/tracked`**：帶 `match_json` → state matched 且 match_json 存入；帶 `tailor_json` → state tailored 且存入；只帶其一時另一保留；既有 SP16 行為（去重/不降級/保留 created_at）回歸不破。
- **`GET /api/tracked/{code}`**：已追蹤且有快取 → 回 parsed match/tailor；未追蹤 → `found: false`、match/tailor 為 null。
- **`/api/snapshot`**：追蹤數筆後 `tracked_codes` 含那些 code；best-effort（build_pipeline 或 load 出錯不影響其他欄位）。
- **前端**：無單元測試，靠 `npm run build` ＋人工；契約由後端測試守。

## 明確不做（Out of Scope）

- 卡片內手動標記 offer/婉拒、offer 並列比較 → **SP19**（`merge_tracked_job` 已預留不降級終端，但無設定入口）。
- 履歷合一、偏好集中 → SP18。
- 研究結果從 Modal 改為卡片內嵌 inline（本 SP 沿用 `ResearchButton` 的 Modal，不重造）。
- 既有 UI/UX 精修（window.alert、a11y 等）。
