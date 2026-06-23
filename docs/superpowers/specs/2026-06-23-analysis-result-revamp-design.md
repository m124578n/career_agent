# 分析結果區改版：摺疊卡片 + 福利 tag + 候選收合

日期：2026-06-23
狀態：設計定稿，待實作

## 目標

職缺契合度頁的「候選清單」與「排序結果」在筆數多時版面過長、資訊密度高。
本次改版：(1) 分析結果卡片可摺疊/展開；(2) 分析時由 LLM 抽出職缺福利並以
tag 呈現；(3) 候選清單可一鍵收合；(4) 「排序結果」正名為「分析結果」。

## 背景與現況

- 職缺契合度頁 `frontend/src/pages/JobList.tsx`：候選清單（每筆一行勾選）與排序
  結果（`MatchCard`，每張含標題/分數/meter/reasons/gaps/按鈕）上下堆疊。
- 後端分析 `backend/src/job_tracker/services/job_matching.py`：`_build_prompt`
  組 prompt → `llm.parse(MatchAnalysis)` 產生 score/reasons/gaps → 組 `JobMatch`。
- 福利資訊寫在 `JobDetail.description`（完整 JD），目前未結構化抽出。
- 已完成的相鄰改版：候選欄內捲動、排序結果漸進顯示（前 12 筆 + 顯示更多）。

## 設計決策（已與使用者確認）

1. 佈局維持**上下堆疊**（不左右並排）；候選清單可收合。
2. 福利 tag 由**分析時 LLM 抽取**（非前端關鍵字比對——前端拿不到完整 JD）。
3. 分析卡片**預設摺疊**，福利 tag 在摺疊狀態即可見。
4. 「排序結果」正名為「分析結果」。

## 後端

### Schema（`schemas/__init__.py`）
- `MatchAnalysis` 加：`benefits: list[str] = Field(default_factory=list,
  description="JD 明確提到的福利，標籤化")`
- `JobMatch` 加：`benefits: list[str] = Field(default_factory=list)`
  （舊資料無此欄位 → 預設空，向後相容）

### Prompt（`services/job_matching.py`）
`_build_prompt` 末段加一句，要求抽福利：
> 並列出職缺**明確提到**的福利（如特休、年終、遠端、彈性上班、股票等），
> 每項標籤化、≤ 8 字、最多 6 項；JD 沒提到就不要列（不要臆測）。

`analyze()` 組 `JobMatch` 時帶入 `benefits=analysis.benefits`。

### Repository（`db/repositories.py`）
`MatchRepository.set_result` 的 `$set` 加 `"benefits": analysis.benefits`。

## 前端

### Types（`types/index.ts`）
`JobMatch` 加 `benefits: string[]`（對齊後端 snake/欄位名 `benefits`）。

### 分析卡片摺疊（`pages/JobList.tsx` 的 `MatchCard`）
- 加 `const [expanded, setExpanded] = useState(false)`（預設摺疊）。
- **恆顯示（摺疊頭部）**：標題（連結）、公司 · 薪資、分數、福利 tag、「▾ 展開／▴ 收合」切換。
- **展開才顯示**：meter 分數條、reasons/gaps（`jt-tags`）、chips（需官網投遞/已寫信）、
  按鈕列（加入追蹤/生成求職信）。
- 福利 tag：用偏綠的小 chip（與 reasons/gaps 的 `jt-tag` 區隔），顯示 `benefits`，
  最多顯示 6 個（後端已限制，前端不再截斷）。
- pending/failed 狀態的卡片維持現狀（不套摺疊，無 benefits）。

### 候選清單收合（`JobList.tsx` 候選 panel）
- 加 `const [candOpen, setCandOpen] = useState(true)`（預設展開）。
- 候選 `panel-head` 加「▾ 收合／▸ 展開」切換；收合時不渲染候選 `panel-body`。
- 版面歸屬：`panel-head` 含「候選計數 + 爬下一頁 + 分析選中(n)」按鈕，收合後**仍可見**；
  `panel-body` 含「全選列 + 候選清單」，收合後整個隱藏（全選對收合狀態無意義，故一併藏）。

### 正名
- 候選下方面板標題 `排序結果 // RANKED` → `分析結果 // RANKED`。

## 樣式

福利 tag 新增一個 class（或沿用 `jt-chip` 並加 data 屬性著色），偏綠/teal 系，
與正面 reasons（`jt-tag[data-kind="pos"]`）視覺上可區分但不衝突。具體色票
實作時取 `--jt-teal` 系。

## 刻意不做（YAGNI）

- 不做左右並排佈局。
- 福利不做前端關鍵字 fallback。
- 福利/結果不做篩選或搜尋。
- 不對 pending/failed 卡片做摺疊。

## 測試

- 後端：
  - `MatchAnalysis`/`JobMatch` 預設 `benefits == []`（schema 測試）。
  - `analyze()` 把 `analysis.benefits` 帶進回傳的 `JobMatch`（用 fake/stub LLM
    回含 benefits 的 MatchAnalysis，斷言透傳）。
  - `set_result` 寫入 benefits（repository 測試）。
- 前端：型別檢查 `tsc --noEmit` exit 0；手動驗證摺疊/展開、福利 tag 顯示、
  候選收合、標題正名。

## 相容性

- 既有 `JobMatch` 文件無 `benefits` → Pydantic 預設 `[]`，前端 `benefits` 顯示空，
  無需資料遷移。
