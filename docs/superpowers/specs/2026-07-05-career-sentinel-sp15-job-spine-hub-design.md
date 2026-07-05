# SP15：職缺脊椎 ＋ 求職中心 設計

**日期：** 2026-07-05
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 正在從「8 個分頁工具」重構成「聊天當總指揮的求職流水線」。整體拆成 5 個子專案：

| SP | 內容 |
|---|---|
| **SP15（本篇）** | 職缺脊椎（持久化職缺物件）＋ 求職中心（儀表板擴張成管道主視圖） |
| SP16 | 找職缺三入口合一 ＋ 職缺連動卡片（比對→研究→客製化 串起來） |
| SP17 | 履歷兩入口合一 ＋ 偏好集中 |
| SP18 | offer 比較 |
| SP19 | 聊天當總指揮（整條流水線工具化給 agent ＋ 共用脈絡） |

**SP15 是地基**：後面的串接、追蹤、offer 比較都掛在這根脊椎上。SP15 本身交付「資料表 ＋ 合併引擎 ＋ 視圖」，資料先靠現有 104 scrape 餵，一上線就有東西看。

## 目標

一句話：**讓職缺變成一個持久化、有狀態的物件，並把儀表板擴張成一份「按狀態分組的職缺管道」主視圖。**

## 現況（實作依據）

- `store.py` 的 snapshot 是**版本化**的：每次 scrape 產生一個 snapshot，`applications` / `interviews` / `viewers` / `messages` 都是 per-snapshot 的列。`latest_two_ids()` 取最新兩版。
- `applications` 表有 `job_id`（＝104 job code）、`company`、`title`、`status`、`applied_at`。
- `interviews` 表有 `company`、`job_title`、`when`(interview_time)、`location`、`status`、`job_url`；**不保證有 code**，跨抓取穩定鍵是 `interview_key(iv)` = `company|job_title|when`。
- `dismissed_interviews`（單列 JSON）記已隱藏的面試 key。
- `/api/snapshot` 的 `_snapshot_payload()` 輸出 `viewers` / `applications` / `messages` / `interviews`（面試已含 `gcal_link`、`key`、`dismissed`、`company_url`、`thread_url`、`job_url`，並依 `when` 排序）＋ `digest` / `failed_readers`。
- 前端 `Dashboard.tsx`：4 個 KPI（誰看過我／即將面試／新訊息／投遞中）→「今日彙整」→「即將到來的面試」（含 gcal／知道了-還原／看職缺／對話串）→ Grid 左「誰看過我」右「我的應徵 ＋ 訊息·面試」。

## 資料模型

### 新表 `tracked_jobs`（app 端持久層）

```sql
CREATE TABLE IF NOT EXISTS tracked_jobs (
    code TEXT PRIMARY KEY,
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    salary TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'interested',
    match_score INTEGER,
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
```

- `code` = 104 job code，作主鍵（去重）。
- `state` 只存**手動狀態**：`interested` / `matched` / `tailored` / `offer` / `rejected`。
- `match_score` 可空（SP16 比對後寫入，SP15 先留欄位）。

> **SP15 沒有這張表的寫入者**——手動「追蹤」與 比對/客製化 自動 tag 是 SP16。SP15 只建表、model、store 讀寫函式、合併引擎、視圖。上線時此表為空，管道只顯示 104 帶入的 已投遞/面試中。

### 新 model（`models.py`）

```python
class TrackedJob(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    state: str = "interested"   # interested|matched|tailored|offer|rejected
    match_score: int | None = None
    created_at: str = ""
    updated_at: str = ""

class PipelineJob(BaseModel):
    """合併引擎輸出的統一 DTO（前端據 state 分組渲染）。"""
    key: str                    # code；interview 無 code 時退回 company|job_title
    code: str = ""              # 104 job code（可空）
    company: str = ""
    title: str = ""
    state: str = "interested"   # 有效狀態（見狀態機）
    url: str = ""
    salary: str = ""
    match_score: int | None = None
    # 已投遞側（來自 applications）
    status: str = ""
    applied_at: str = ""
    # 面試側（來自 interviews）
    when: str = ""
    location: str = ""
    gcal_link: str = ""
    interview_key: str = ""
    dismissed: bool = False
    # 連結與旗標
    company_url: str = ""
    job_url: str = ""
    thread_url: str = ""
    watched: bool = False
```

## 狀態機

有序 rank（數字越大越前面）：

| state | 中文 | rank | 來源 |
|---|---|---|---|
| `interested` | 有興趣 | 1 | 手動（SP16） |
| `matched` | 已比對 | 2 | 手動 tag（SP16） |
| `tailored` | 已客製化 | 3 | 手動 tag（SP16） |
| `applied` | 已投遞 | 4 | **104 applications** |
| `interviewing` | 面試中 | 5 | **104 interviews** |
| `offer` | offer | 終端 | 手動 |
| `rejected` | 婉拒 | 終端 | 手動 |

**有效狀態計算：**
1. 若 `tracked_jobs.state` 是終端（`offer` / `rejected`）→ 直接採用（手動決定優先）。
2. 否則 `effective = 兩者 rank 較大`：`max(rank(tracked_jobs.state), rank(104 訊號))`。
   - 104 訊號：該 code 出現在最新 snapshot 的 applications → `applied(4)`；出現在 interviews → `interviewing(5)`。
   - `tracked_jobs` 沒該筆時只看 104 訊號；104 沒訊號時只看 `tracked_jobs.state`。

## 合併引擎（新 `pipeline.py`）

```python
def build_pipeline(conn) -> list[PipelineJob]:
    """讀最新 snapshot 的 applications+interviews ＋ tracked_jobs，合併成統一清單。
    純讀、best-effort；任何例外都不得往上冒（不能影響 snapshot / scrape）。"""
```

演算法：

1. 取最新 snapshot（`latest_two_ids()[0]`）；無 snapshot 時 applications/interviews 視為空。
2. 建 `dict[str, PipelineJob]`，key = code（或退回鍵）。
3. **applications**：每筆 → 或建或補一個 job，帶入 `code=job_id`、company、title、`status`、`applied_at`、`job_url`/`company_url`（用 `company_link`）、`watched`（用 `watch.is_watched`）；記 104 訊號 rank ≥ 4。
4. **interviews**：每筆 → code 盡量從 `job_url` 抽（`jobfetch.extract_job_code(iv.job_url)`；回空字串就用 `interview_key(iv)` 當 key）；帶入 `when`、`location`、`gcal_link`（`calendar_link.build_gcal_link`）、`interview_key`、`dismissed`（查 `dismissed_interviews`）、`thread_url`/`company_url`；記 104 訊號 rank ≥ 5。同 code 已存在（來自 application）就補面試欄位。
5. **tracked_jobs**：每筆併入對應 code（或新增），帶 `salary`、`match_score`、手動 state。
6. 對每筆算**有效狀態**（上節規則），寫回 `state`。
7. 回傳清單。排序由前端分組時處理。

`_snapshot_payload()` 新增 `"pipeline": [pj.model_dump() for pj in pipeline.build_pipeline(conn)]`（包在 try/except，失敗回 `[]`，不得讓 snapshot 掛掉）。既有的 `applications` / `interviews` / `viewers` / `messages` 欄位**保留輸出**（不破壞相容），前端改用 `pipeline` 渲染職缺、用 `viewers`/`messages` 渲染訊號。

## 求職中心版面（改 `Dashboard.tsx`）

由上到下：

1. **KPI 區**（維持現有 4 個，不動）：誰看過我／即將面試／投遞中／新訊息。
2. **職缺管道**（新，取代現在分開的「即將到來的面試」＋「我的應徵」）：
   - 單一清單，按**有效狀態分組**，群組由前到後：`面試中 → 已投遞 → 已客製化 → 已比對 → 有興趣`。空群組不顯示。終端 `offer`/`婉拒` SP15 先不獨立顯示（SP18 處理）。
   - **`面試中` 群組必須完整保留 SP7 功能**：`gcal_link`（加入 Google 日曆）、知道了/還原（dismiss/restore，含「已處理 N 場」收合）、看職缺、104 對話串。dismissed 的面試不佔 `面試中` 主清單，走現有收合。
   - **`已投遞` 群組**保留 `status` badge、公司/職缺連結、watched 星號。
   - `已客製化`/`已比對`/`有興趣` 群組 SP15 資料為空（tracked_jobs 沒寫入者），先不會出現。
3. **次要訊號區**（誰看過我、訊息移到管道下方）：沿用現有 Row 樣式與 ResearchButton；行為不變。

視覺沿用現有 Cockpit 主題與 `PageContainer`/`Kpi`/`Row`/`SectionTitle`/`ShowAll` 元件，不新增設計語彙。

## Global Constraints（實作時必守）

- **不得弄丟 SP7 面試功能**：gcal 連結、dismiss/restore、thread_url、看職缺，全部在 `面試中` 群組保留可用。
- **合併引擎純讀、best-effort**：`build_pipeline` 與 payload 注入都用 try/except 包住，任何錯誤回空清單/空欄位，**絕不影響 snapshot 讀取或 scrape**。
- **相容**：`/api/snapshot` 既有欄位（applications/interviews/viewers/messages/digest/failed_readers）保留；只**新增** `pipeline`。
- **tracked_jobs 空表要能正常運作**：管道只顯示 104 帶入的 已投遞/面試中，上線即有內容。
- **104 job code 為職缺主鍵**；interview 無 code 時以 `company|job_title` 退回鍵，不得因缺 code 而崩。
- 後端仍綁 `127.0.0.1`；不寫入 104。

## 測試策略

- `pipeline.build_pipeline`：
  - 只有 applications → 全部 `applied`。
  - 只有 interviews（有 code / 無 code 兩種）→ `interviewing`，退回鍵正確。
  - 同 code 同時在 applications＋interviews → 合併成一筆、狀態取 `interviewing`。
  - tracked_jobs 有手動 `tailored` 但 104 已 `applied` → 有效狀態取 `applied`（rank 較大）。
  - tracked_jobs 手動 `offer` ＋ 104 `interviewing` → 有效狀態 `offer`（終端優先）。
  - 空 DB / 無 snapshot → 回 `[]`，不丟例外。
- `store`：`tracked_jobs` 建表、upsert、讀取（依 code）。
- payload：`build_pipeline` 丟例外時 `_snapshot_payload` 仍回完整其他欄位、`pipeline=[]`。
- 前端：型別與渲染以現有測試風格為準（若專案有前端測試則補；否則以後端契約為主）。

## 明確不做（Out of Scope，留給後續 SP）

- 手動「追蹤」職缺、比對/客製化自動 tag → **SP16**。
- 找職缺三入口合一、職缺連動卡片 → **SP16**。
- offer 比較視圖、終端狀態顯示 → **SP18**。
- 履歷合一、偏好集中 → **SP17**。
- agent 工具化 → **SP19**。
- 前端既有 UI/UX 精修（window.alert、a11y 等）不在本 SP 範圍。
