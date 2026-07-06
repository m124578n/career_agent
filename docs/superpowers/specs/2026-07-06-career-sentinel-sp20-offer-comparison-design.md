# SP20：offer 比較 設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 求職流水線第六個子專案。求職流程的尾聲：把拿到的 offer 捕捉成結構化明細（談定的年薪/月薪/地點/職級/到職日/備註——這些 104 上沒有、需使用者親手填），並在求職中心以**並排比較表**呈現所有 offer，自動高亮最高年薪。同時補上目前缺席的「錄取／未錄取」狀態入口——狀態機早已有 `TERMINAL = {offer, rejected}`，但沒有任何 UI 能設定它們。

roadmap：SP15 ✅ → SP16 ✅ → SP17 ✅ → SP18 ✅ → SP19 ✅ → **SP20（本篇）offer 比較** → SP21 聊天當總指揮 → SP22（未來）offer 談判建議（吃本 SP 的 offer 明細給議價策略）。

## 目標

一句話：**在卡片 Drawer 提供「標記錄取（填 offer 明細）／標記未錄取／重設」入口，並在求職中心用並排比較表呈現所有 offer、高亮最高年薪。**

## 現況（實作依據）

- **狀態機（`pipeline.py`）**：`STATE_RANK = {interested:1, matched:2, tailored:3, applied:4, interviewing:5}`、`TERMINAL = {offer, rejected}`。`effective_state(manual, signal_rank)`：終端手動狀態優先，否則取 `max(manual_rank, signal_rank)` 的狀態名。
- **`merge_tracked_job`（`store.py:303`）**：加法式 upsert，**防降級**——`existing.state in TERMINAL` 就保留、否則只在新 state rank ≥ 舊 rank 時前進。這是為了防 104 訊號把手動狀態往回拉；**因此它無法把狀態設成 offer/rejected（rank 比較擋掉），也無法從終端清回去**。本 SP 需要一條「強制設定」路徑並存。
- **`TrackedJob`（`models.py:183`）**：`code`（PK）/`company`/`title`/`url`/`salary`（字串）/`state`/`match_score`/`match_json`/`tailor_json`/`created_at`/`updated_at`。無結構化 offer 欄位。
- **`PipelineJob`（`models.py:197`）**：合併引擎輸出的扁平 DTO；已有 `state`/`match_score`/`location`（來自 interviews）等。`build_pipeline` 併 tracked 時目前只帶 `url/salary/match_score/company/title`。
- **`POST /api/tracked`（app.py:495）**：`_TrackReq`，依 match/tailor 有無推 `state_hint`（interested/matched/tailored），呼叫 `merge_tracked_job`。從不送 offer/rejected。
- **`GET /api/tracked/{code}`（app.py:512）**：回 `{code, found, state, match_score, match, tailor}`。
- **`DELETE /api/tracked/{code}`（app.py:524）**：`store.delete_tracked_job`。
- **前端 `JobCardDrawer.tsx`**：右側 Drawer，比對/研究/客製化三區；開啟時 `getTrackedJob` 載快取。**無狀態控制區。**
- **`Dashboard.tsx`**：`pipe = s.pipeline`，依 state 分群渲染（面試中/已投遞/已客製化/已比對/有興趣）＋收合「已處理」（dismissed 面試）。**無 offer/rejected 群組。**
- **Migration（`store.py`）**：`_migrate` 用 `PRAGMA table_info` + 冪等 `ALTER TABLE ... ADD COLUMN`（現加 match_json/tailor_json）。`connect()` 內呼叫。

## 資料模型

### 新 `OfferDetail`（`models.py`）

```python
class OfferDetail(BaseModel):
    salary_year: int | None = None   # 年薪
    salary_month: int | None = None  # 月薪
    location: str = ""
    level: str = ""                  # 職級
    start_date: str = ""             # 到職日
    notes: str = ""
```

### `TrackedJob` 加 `offer_json`（`models.py`）

比照 `match_json`/`tailor_json`，新增 `offer_json: str = ""`（序列化的 `OfferDetail`；空字串＝無 offer 明細）。

### `PipelineJob` 加 `offer`（`models.py`）

```python
offer: OfferDetail | None = None   # offer-state job 的談定明細
```

### Migration（`store.py`，冪等）

`_migrate` 的欄位迴圈把 `offer_json` 併入既有清單：

```python
for col in ("match_json", "tailor_json", "offer_json"):
    if col not in cols:
        conn.execute(f"ALTER TABLE tracked_jobs ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
```

同時 `_SCHEMA` 的 `tracked_jobs` CREATE 加一行 `offer_json TEXT NOT NULL DEFAULT ''`（新裝機直接有；`_migrate` 保障舊機升級）。

`load_tracked_jobs`/`get_tracked_job`/`upsert_tracked_job` 的 SELECT/INSERT 欄位清單全部補上 `offer_json`（比照 match_json/tailor_json 的 `or ""` NULL-guard）。

## 後端變更

### 1. `store.set_tracked_state`（強制設定，繞過 rank 防降級）

`merge_tracked_job` 的 rank 邏輯是給「訊號帶動的自動前進」用；使用者手動設定終端狀態要能直接覆寫、也能清回去，故另立一條路徑：

```python
def set_tracked_state(
    conn: sqlite3.Connection, code: str, state: str, *, offer: OfferDetail | None = None,
) -> str:
    """強制設定追蹤職缺狀態（使用者手動；繞過 merge 的 rank 防降級）。
    state="offer" 時 offer 明細序列化存 offer_json；state 非 offer 時清空 offer_json。
    保留既有 created_at 與其他欄位；不存在則新建。回最終 state。"""
    now = datetime.now().isoformat(timespec="seconds")
    existing = get_tracked_job(conn, code)
    offer_json = json.dumps(offer.model_dump(), ensure_ascii=False) if (state == "offer" and offer is not None) else ""
    if existing is not None:
        upsert_tracked_job(conn, TrackedJob(
            code=code, company=existing.company, title=existing.title, url=existing.url,
            salary=existing.salary, state=state, match_score=existing.match_score,
            created_at=existing.created_at or now, updated_at=now,
            match_json=existing.match_json, tailor_json=existing.tailor_json, offer_json=offer_json,
        ))
    else:
        upsert_tracked_job(conn, TrackedJob(
            code=code, state=state, created_at=now, updated_at=now, offer_json=offer_json,
        ))
    return state
```

- `offer` 只在 `state == "offer"` 時寫入；設 rejected 或 reset 都清空 offer_json（避免殘留舊 offer）。

### 2. 三個端點（`web/app.py`）

```python
@app.post("/api/tracked/{code}/offer")
def tracked_set_offer(code: str, offer: OfferDetail) -> dict:
    final = store.set_tracked_state(_conn(), code, "offer", offer=offer)
    return {"status": "ok", "state": final}

@app.post("/api/tracked/{code}/reject")
def tracked_set_reject(code: str) -> dict:
    final = store.set_tracked_state(_conn(), code, "rejected")
    return {"status": "ok", "state": final}

@app.post("/api/tracked/{code}/reset")
def tracked_reset(code: str) -> dict:
    final = store.set_tracked_state(_conn(), code, "interested")
    return {"status": "ok", "state": final}
```

- 三者皆不校驗 code 是否已存在（不存在就新建純手動 job）；但 `code` 空字串應擋（比照 `POST /api/tracked` 的 400「缺少職缺代碼」）。用 path 參數，`code.strip()` 為空回 400。
- `OfferDetail` 需 import 進 app.py 的 models import 清單。

### 3. `build_pipeline` 帶出 offer 明細（`pipeline.py`）

tracked 併入迴圈與純手動新增迴圈，當 `tj.offer_json` 非空時解析成 `OfferDetail` 設到 `pj.offer`：

```python
if tj.offer_json:
    try:
        pj.offer = OfferDetail.model_validate_json(tj.offer_json)
    except Exception:
        pj.offer = None
```

（`build_pipeline` 整體已包在 try/except → []，此處再加 per-job try 保險，壞資料不整批消失。）`OfferDetail` import 進 pipeline.py。

### 4. `GET /api/tracked/{code}` 回 offer（`web/app.py`）

回傳 dict 加 `"offer": json.loads(tj.offer_json) if tj.offer_json else None`，供 Drawer 開啟時預填表單。

## 前端變更

### 5. api.ts

- 新型別 `OfferDetail`：`{ salary_year: number | null; salary_month: number | null; location: string; level: string; start_date: string; notes: string }`。
- `PipelineJob` 型別加 `offer?: OfferDetail | null`。
- `getTrackedJob` 回傳型別加 `offer?: OfferDetail | null`。
- 新函式：`setOffer(code, offer): Promise<Response>`（`POST /api/tracked/{code}/offer`，body=offer）、`rejectJob(code): Promise<Response>`（`POST .../reject`）、`resetTracked(code): Promise<Response>`（`POST .../reset`）。

### 6. JobCardDrawer 狀態區（`JobCardDrawer.tsx`）

在既有三區之上（或之下）新增「狀態」`Paper`：
- 開啟時 `getTrackedJob(code)` 已載快取；讀 `c.state` 與 `c.offer` 存 local state。
- **未終端時**：兩顆按鈕「標記錄取」「標記未錄取」。點「標記錄取」展開 inline 表單：`NumberInput` 年薪、`NumberInput` 月薪、`TextInput` 地點、`TextInput` 職級、`TextInput` 到職日、`Textarea` 備註，＋「儲存」按鈕 → `setOffer(code, form)`；成功 invalidate `snapshot`＋關 Drawer 或就地更新狀態。點「標記未錄取」→ `rejectJob(code)`。
- **已是 offer 時**：顯示目前 offer 明細摘要＋「編輯」（重開表單，預填 `c.offer`）＋「重設」按鈕 → `resetTracked(code)`。
- **已是 rejected 時**：顯示「已標記未錄取」＋「重設」按鈕。
- 所有呼叫 `r.ok` 檢查（比照既有 runMatch/runTailor 慣例），失敗 `setErr`。

### 7. Dashboard offer 比較表 ＋ 未錄取群組（`Dashboard.tsx`）

- `const offerJobs = pipe.filter((j) => j.state === "offer")`、`const rejectedJobs = pipe.filter((j) => j.state === "rejected")`。
- **offer 區**（放在管道頂部，offer 是最終目標）：不用 `Row` 平列，改用 Mantine `Table`（或 Grid 表格）並排比較。每列一個 offer，欄位：`公司·職稱`（點列開卡片）/ `年薪` / `月薪` / `地點` / `職級` / `到職日` / `比對分數` / `備註`。
  - **高亮最高年薪**：計算各 offer 的「折算年薪」＝ `salary_year ?? (salary_month != null ? salary_month * 12 : null)`；取最大值那列的年薪（或折算來源）儲存格加 teal 強調（`c="teal.5" fw={700}` 或 teal 背景）。全部無薪資則不高亮。純顯示，不改資料。
  - 空欄顯示 `—`。
- **未錄取區**：比照現有「已處理」收合模式（`Button variant="subtle"` 切換 + 收合列表），每列灰階顯示公司·職稱，附「重設」`ActionIcon`（`resetTracked`）。
- offer/rejected 群組的存在條件併入 `Dashboard.tsx:156` 那個「管道有內容才渲染」的判斷。
- 視覺沿用 Cockpit 主題（`Paper bg="dark.6"`、teal 強調、`SectionTitle`）。

## Global Constraints（實作時必守）

- **兩條寫入路徑並存、語意分明**：`merge_tracked_job`（訊號帶動、防降級，維持 SP15/SP17 行為不動）與 `set_tracked_state`（使用者手動、強制設定/清除終端）。**不改 `merge_tracked_job` 既有邏輯**（比對/客製化追蹤仍走它）。
- **offer_json 生命週期**：只有 `state == "offer"` 才有 offer_json；設 rejected / reset 一律清空，杜絕殘留舊 offer 顯示在比較表。
- **相容**：`TrackedJob` 加 `offer_json`、`PipelineJob` 加 `offer` 皆加法式；`offer_json` 靠 `_migrate` 冪等 ALTER（不丟資料）；Pydantic v2 忽略多餘 key。`POST /api/tracked`、`GET/DELETE /api/tracked/{code}` 既有回傳只增不減（`GET` 多回 `offer`）。
- **build_pipeline 韌性不變**：整體 try/except → []；offer 解析再加 per-job try，壞資料不整批消失。
- **最高年薪高亮純前端、純顯示**：不寫回、不改 offer 明細；折算月薪×12 只用於比大小。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`；後端綁 `127.0.0.1`；前端 `npm run build` 必過（刪除/新增後清乾淨殘留 import）。

## 測試策略（後端用專案 venv：`sentinel/.venv/Scripts/python.exe -m pytest -q`）

- **`set_tracked_state`**：
  - 設 offer＋OfferDetail → `get_tracked_job` 的 `state=="offer"`、`offer_json` round-trip 回相同明細。
  - 設 rejected → `state=="rejected"`、`offer_json==""`。
  - 從 offer reset → `state=="interested"`、`offer_json==""`（明細清除）。
  - 對不存在的 code 設 offer → 新建成功。
  - 保留 created_at：先 track 再 set offer，created_at 不變、updated_at 更新。
- **三端點**：`POST .../offer`（body OfferDetail）存明細並回 state=offer；`.../reject` 回 rejected；`.../reset` 回 interested 且明細清空。code 空字串 → 400。
- **`GET /api/tracked/{code}`**：offer-state job 回 `offer` 明細；非 offer 回 `offer: None`。
- **`build_pipeline`**：offer-state tracked job（有 offer_json）→ 對應 `PipelineJob.offer` 帶出明細且 `state=="offer"`；reset 後（offer_json 空、state interested）→ `offer is None` 且狀態回歸訊號態（有 104 訊號時取訊號）。offer_json 為壞字串 → 該 job `offer is None`、其餘 job 不受影響。
- **`merge_tracked_job` 回歸**：既有測試維持綠（終端防降級、rank 前進行為不變）。
- **最高年薪高亮**：純前端邏輯，靠 `npm run build` ＋人工。契約由後端測試守。

## 明確不做（Out of Scope）

- offer 談判建議 / 議價策略 / 自動評分排名 → **SP22（未來）**（只高亮最高年薪，不給建議）。
- 多幣別 / 匯率換算、稅後試算、股票/獎金結構化拆解 → 不做（`notes` 自由填）。
- rejected 明細表單（婉拒原因結構化）→ 不做（reset 即可）。
- 聊天當總指揮 → SP21。
- 既有 UI/UX 精修（window.alert、a11y 等）。
