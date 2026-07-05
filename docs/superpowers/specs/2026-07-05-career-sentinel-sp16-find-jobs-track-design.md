# SP16：找職缺合一 ＋ 追蹤 設計

**日期：** 2026-07-05
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 重構成「聊天當總指揮的求職流水線」的第二個子專案。SP15 已鋪好職缺脊椎（`tracked_jobs` 表 ＋ `pipeline.build_pipeline` 合併引擎 ＋ 求職中心視圖）。SP16 把「找職缺」三個入口合一，並讓找到的職缺能**手動追蹤進脊椎**，於求職中心以狀態群組顯示。

整體 roadmap（SP16 拆分後重排）：

| SP | 內容 |
|---|---|
| SP15 ✅ | 職缺脊椎 ＋ 求職中心 |
| **SP16（本篇）** | 找職缺三入口合一 ＋ 追蹤進脊椎（含 SP15 遺留的求職中心群組/排序前置） |
| SP17 | 職缺連動卡片（求職中心的卡片：研究/客製化/重新比對串接、auto-tag；此時才把「客製化」摺進卡片） |
| SP18 | 履歷合一 ＋ 偏好集中 |
| SP19 | offer 比較 |
| SP20 | 聊天當總指揮 |

## 目標

一句話：**把 搜尋／推薦／JD 比對 收成一個「找職缺」頁，找到的職缺一鍵追蹤進脊椎，於求職中心按狀態顯示。**

交付後可跑通的完整迴圈：**找（三來源）→（可當場比對）→ 追蹤 → 求職中心看到它在「有興趣／已比對」群組**。

## 現況（實作依據）

- **後端端點**（`web/app.py`，皆保留不動）：
  - `GET /api/search?kw=` → `{jobs: [RecommendedJob…]}`（`fetch_search`）
  - `GET /api/recommend` → `{jobs: [RecommendedJob…]}`（`recommend_session`，需瀏覽器）
  - `POST /api/match` 收 `{job_url}` → `MatchResult`（`score/reasons/gaps`，另含 title/company/salary）
  - `POST /api/tailor` 收 `{job_url}` → `TailoredApplication`
  - `jobfetch.extract_job_code(url)`（非 104 網址 raise `ValueError`）、`jobfetch.fetch_job_detail(code) -> JobDetail`（title/company/salary/location/…）
- **`RecommendedJob`（models.py）**：`code, url, title="", company="", salary="", is_watched=False`。
- **`tracked_jobs` 表（SP15）**：`code`(PK)/company/title/url/salary/state/match_score/created_at/updated_at。store 有 `load_tracked_jobs`/`get_tracked_job`/`upsert_tracked_job`。
- **`pipeline.build_pipeline`（SP15）**：已能對 tracked-only 職缺產出 `interested`/`matched`/`tailored` 狀態的 `PipelineJob`（有測 `test_build_tracked_only_job_appears`）。
- **前端**：`SearchPage`/`RecommendPage` 用共用 `JobRow`（含 inline `比對` 鈕、去 104 看、ResearchButton）；`MatchPage`（貼網址→吻合度）；`TailorPage`（貼網址→tips＋求職信）。導覽 `Sidebar.tsx` 的 `NAV` 有 `match/recommend/search/tailor` 四項；`App.tsx` 以 `display:none` 保持全頁掛載。
- **求職中心（SP15 交付）**：`Dashboard.tsx` 已有「職缺管道」按狀態分組（目前只渲染 `面試中`／`已投遞` 兩群組）＋次要訊號區。SP15 最終審查留下：`有興趣/已比對/已客製化` 三群組尚未渲染、面試中/已投遞未依 `when` 排序。

## 資料流

```
找職缺（關鍵字/推薦/貼網址）
  → JobRow：可 inline 比對（POST /api/match）得 score
  → 按「追蹤」→ POST /api/tracked（帶 code/company/title/url/salary，有比對過就帶 match_score）
       → upsert tracked_jobs（有 score→state=matched，否則 interested）
  → 求職中心 /api/snapshot 的 pipeline 併入該 tracked job
       → 顯示於「已比對」或「有興趣」群組
```

## 後端變更

### 1. 追蹤寫入／取消（`web/app.py`）

新增請求模型與三個端點：

```python
class _TrackReq(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    match_score: int | None = None
```

- `POST /api/tracked`（收 `_TrackReq`）：
  - `code` 空 → 400「缺少職缺代碼」。
  - 決定 state：`match_score is not None` → `"matched"`，否則 → `"interested"`。
  - 若該 code 已存在於 tracked_jobs，**保留原 created_at 與較前面的 state**：讀 `get_tracked_job(code)`；`created_at` 沿用既有（無則用現在時間），`state` 取「較前面」（用 `pipeline.STATE_RANK`；但不覆蓋既有終端 offer/rejected），`match_score` 有新值就更新、否則保留舊值。`updated_at` = 現在。
  - `upsert_tracked_job(conn, TrackedJob(...))`。回 `{"status": "tracked", "state": <最終state>}`。
- `DELETE /api/tracked/{code}`：從 tracked_jobs 刪除該 code；回 `{"status": "untracked"}`。需在 `store.py` 新增 `delete_tracked_job(conn, code)`。
- `GET /api/job?url=`：貼網址來源用。`extract_job_code(url)`（ValueError→400），`fetch_job_detail(code)`（失敗→502），回 `{"code": code, "url": url, "title": jd.title, "company": jd.company, "salary": jd.salary, "is_watched": watch.is_watched(jd.company, jd.title, settings)}`（RecommendedJob 形狀）。

時間戳沿用專案慣例：`datetime.now().isoformat(timespec="seconds")`（同 chat.py/research.py/usage.py）。

### 2. store 刪除函式（`store.py`）

```python
def delete_tracked_job(conn, code: str) -> None:
    conn.execute("DELETE FROM tracked_jobs WHERE code = ?", (code,))
    conn.commit()
```

## 前端變更

### 3. 求職中心補三群組 ＋ 排序（`Dashboard.tsx`）— SP15 前置

- 「職缺管道」在既有 `面試中`／`已投遞` 之後，補上 `已客製化`（state `tailored`）／`已比對`（state `matched`）／`有興趣`（state `interested`）三個群組（空群組不顯示）。群組由前到後：`面試中 → 已投遞 → 已客製化 → 已比對 → 有興趣`。
  - 這三個新群組每列用簡列樣式（沿用 `Row`／`CompanyLink`／`Star`／`ResearchButton`），顯示公司·職稱；`已比對` 群組若有 `match_score` 顯示小分數徽章（teal）；每列尾端一個「取消追蹤」ActionIcon（`DELETE /api/tracked/{code}`，成功後 invalidate `snapshot`）。
- **排序**：`面試中`（`upcomingJobs`）與 `已投遞`（`appliedJobs`）依 `when`（面試）／`applied_at`（投遞）升冪排序；三個手動群組依 `match_score` 降冪、無分數者其後（次序穩定即可）。排序在前端 `Dashboard.tsx` 做，`build_pipeline` 不動。

### 4. 新「找職缺」頁（`FindJobsPage.tsx`，取代 Search/Recommend/Match 三頁）

- 頂部 `PageHeader`（title「找職缺」、subtitle「搜尋、推薦或貼網址找職缺，比對後一鍵追蹤」）。
- `SegmentedControl` 三來源：`關鍵字搜尋`｜`104 推薦`｜`貼網址`。
  - **關鍵字搜尋**：TextInput（seed 自 `watched_keywords`，比照現 SearchPage）＋搜尋鈕 → `GET /api/search` → JobRow 清單。
  - **104 推薦**：拉取鈕（`GET /api/recommend`，`BusyHint`「抓取中」）→ JobRow 清單。
  - **貼網址**：TextInput（104 職缺網址）＋讀取鈕 → `GET /api/job?url=` → 單筆 JobRow。
- 各來源的結果各自獨立 state（切換來源不互相清空，比照現有做法用單頁多 state）。
- `!has_resume` 時比對鈕停用並顯示現有 amber 提示（沿用 SearchPage 文案）。

### 5. `JobRow` 加「追蹤」鈕（`JobRow.tsx`）

- JobRow 新增 prop：`tracked: boolean`（該 code 是否已在脊椎）。由 `FindJobsPage` 依 `/api/snapshot` 的 pipeline（或 tracked 清單）算出傳入。
- 在既有 `比對` 鈕旁加「追蹤」鈕：
  - 未追蹤：按下 → `POST /api/tracked`，帶 `code/company/title/url/salary`；若此列已比對過（`result` 有值）帶 `match_score: result.score`。成功後 invalidate `snapshot`（讓求職中心與 tracked 狀態更新）。
  - 已追蹤：鈕顯示「已追蹤」（實心/teal），再按 → `DELETE /api/tracked/{code}`（取消），invalidate `snapshot`。
- JobRow 目前只吃 `RecommendedJob`；追蹤所需的 company/title/salary/url 都在 `job` 上，直接取用。

### 6. 導覽收斂（`Sidebar.tsx` ＋ `App.tsx`）

- `Sidebar.tsx`：`PageKey` 移除 `match/recommend/search`、新增 `jobs`；`NAV` 移除那三項、加入 `{ key: "jobs", label: "找職缺", icon: IconSearch }`（放在 `104 履歷` 之後、`客製化` 之前）。`客製化`（tailor）暫留。
- `App.tsx`：移除 `MatchPage`/`RecommendPage`/`SearchPage` 的 import 與三個 `<div display:none>`，改成單一 `<div style={{display: page==="jobs"?…}}><FindJobsPage/></div>`。`due` 橫幅裡「也拉推薦」按鈕原本 `setPage("recommend")` → 改成 `setPage("jobs")`。`tailor`/`match` 等殘留引用一併清乾淨（tsc noUnusedLocals）。
- 舊檔 `SearchPage.tsx`/`RecommendPage.tsx`/`MatchPage.tsx` 移除（其職責已由 `FindJobsPage` 涵蓋）。

## Global Constraints（實作時必守）

- **追蹤/取消是純資料寫入，不碰 104**：`POST/DELETE /api/tracked` 只讀寫本地 SQLite；`GET /api/job` 只讀 104 職缺詳情（既有 `fetch_job_detail`，與現 MatchPage 同等行為），不寫入 104。
- **tracked_jobs 以 104 code 去重**：重複追蹤同 code = upsert 覆寫、不新增列；保留原 `created_at`、不降級既有終端狀態（offer/rejected）。
- **求職中心三群組補上後，pipeline 產出的 matched/tailored/interested 職缺才顯示得出**（這是 SP15 最終審查點名的前置，SP16 必做）。
- **不得弄丟 SP7 面試功能與 SP15 既有管道**：Dashboard 改動只新增群組/排序/取消追蹤，既有 面試中/已投遞 群組與訊號區行為不變。
- **相容**：`/api/snapshot` 契約不變（tracked 職缺本就經 pipeline 輸出）；`GET /api/search`、`GET /api/recommend`、`POST /api/match`、`POST /api/tailor` 端點不動。
- 後端綁 `127.0.0.1`；前端 `npm run build`（tsc noUnusedLocals）必須過。

## 測試策略

- **store**：`delete_tracked_job` 刪除存在/不存在的 code（不存在不報錯）。
- **`POST /api/tracked`**：
  - 帶 match_score → state=matched、tracked_jobs 有該列。
  - 不帶 match_score → state=interested。
  - code 空 → 400。
  - 重複追蹤同 code：第二次帶更前面狀態或更新 score → upsert 覆寫、created_at 保留、不新增列（`load_tracked_jobs` 仍 1 筆）。
  - 已是終端 offer 的 code 再被 `POST /api/tracked`（帶 matched）→ 不降級為 matched（維持 offer）。
- **`DELETE /api/tracked/{code}`**：追蹤後刪除 → `load_tracked_jobs` 回 []。
- **`GET /api/job?url=`**：合法 104 網址（mock `fetch_job_detail`）→ 回 RecommendedJob 形狀含 code；非 104 網址 → 400。
- **端到端**：`POST /api/tracked`（帶 score）後打 `GET /api/snapshot`，pipeline 內出現該 code、state=matched。
- **前端**：無單元測試，靠 `npm run build`（型別/unused 檢查）＋人工把關；契約由後端測試守住。

## 明確不做（Out of Scope）

- 職缺卡片（研究/客製化/重新比對串接、auto-tag tailored）與「客製化」導覽項摺進卡片 → **SP17**。
- offer/婉拒 的手動標記 UI → SP19（`POST /api/tracked` 的 state 計算已預留不降級終端狀態，但沒有設定 offer 的入口）。
- 履歷合一、偏好集中 → SP18。
- 既有 UI/UX 精修（window.alert、a11y 等）不在本 SP。
