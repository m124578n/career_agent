# 設計規格：職缺分析結果可依「分析時間」排序

- 日期：2026-06-27
- 範圍：後端（match schema/repository）＋ 前端（JobList 結果排序）
- 狀態：設計已確認，待寫實作計畫

## 背景與目標

職缺契合度頁（`JobList`）分析完成後，結果固定依「契合度分數」由高到低呈現
（後端 `MatchRepository.list_by_search` 已 `sorted(..., key=score, reverse=True)`）。

使用者常分批分析：每送一批，新結果會依分數插進既有清單中間，難以找到「我剛剛
分析的那批」。本案新增一個**排序切換**，讓使用者可在「契合度」與「最新分析」兩種
視角間切換。

設計原則（已與使用者確認）：
- **預設維持「契合度」**——這是本頁的核心價值主張，不更動預設。
- 「最新分析」是次要視角，解「剛分析的跑哪去了」的痛點，用切換並存、不取代。
- 把預設改成時間會把高契合度職缺埋在最近分析的平庸職缺下，傷害核心任務，故不採。

非目標（Out of scope）：
- 不改分析流程、額度計算、爬蟲、求職信、其他頁面。
- 不改後端預設排序（`list_by_search` 仍回分數由高到低；排序切換在前端做）。
- 不做多欄位排序 UI（只「契合度／最新分析」兩個選項）。

## 後端

### Schema（`backend/src/job_tracker/schemas/__init__.py`，`JobMatch`）

新增欄位：

```python
analyzed_at: datetime | None = None  # 分析完成（status→done）時間；candidate/pending 為 None
```

放在 `status` 附近。`datetime` 與 `_utcnow` 已在檔內。既有舊資料反序列化時此欄位
預設 `None`，相容。

### Repository（`backend/src/job_tracker/db/repositories.py`，`MatchRepository.set_result`）

`set_result`（狀態轉 `done` 的唯一蓋點）在 `$set` 內加上 `analyzed_at`：

```python
"analyzed_at": datetime.now(UTC).isoformat(),
```

`datetime`、`UTC` 已在檔頭 import。存 ISO 字串，與 `add_candidate` 經
`model_dump(mode="json")` 存出的 `crawled_at` 格式一致；讀回 `JobMatch(**doc)` 時
pydantic 可解析。

- `set_pending` / `set_failed` / `add_candidate`：不動（這些狀態無分析完成時間）。
- `list_by_search`：不動（預設仍分數由高到低；前端負責排序切換）。
- `set_result` 的 `set_cover_letter` 等其他方法：不動。

### API

`search_matches` 端點回傳 `list[JobMatch]`，新欄位隨同一 response model 自動帶出，
**不需改路由**。

## 前端

### 型別（`frontend/src/types/index.ts`，`JobMatch`）

新增：

```ts
analyzed_at?: string | null;
```

（對應後端，手動保持同步——檔頭註解已載明此約定。）

### 排序切換 UI（`frontend/src/pages/JobList.tsx`，結果面板）

- 在結果面板標頭（現「契合度排序 · N 筆」那一行）右側加一個小型
  `SegmentedControl`，兩個選項：`契合度`（預設）／`最新分析`，`size="xs"`。
- 標頭改為左右配置（eyebrow 左、切換右），窄螢幕允許換行（沿用 RWD 的
  `flexWrap: "wrap", rowGap` 手法）。

### 排序狀態與持久化

- 新增 state：`const [sortMode, setSortMode] = useState<"fit" | "recent">(...)`，
  初值從 `localStorage` 還原（沿用本頁 `KW_KEY` 等慣例，新增 key
  `"jobtracker.job-sort"`，無值時預設 `"fit"`）。
- `useEffect` 同步寫回 `localStorage`（與既有 keyword/area 持久化一致）。

### 排序規則

對 `results`（`status !== "candidate"` 的清單）套用：

- **`fit`（契合度）**：分數由高到低（`score` desc）。等同現狀；明確排序以防後端
  順序變動。
- **`recent`（最新分析）**：分層排序——
  1. `pending`（剛送出、分析中）置頂；
  2. `done` 依 `analyzed_at` 由新到舊（`analyzed_at` 為 `null` 的舊資料殿後）；
  3. `failed` 最後；
  4. 同層之間以 `score` 由高到低為次序。

實作為純前端 `useMemo`/排序函式，作用在 `results` 上後再 `slice(0, resultLimit)`。
不改 `matchesQ`、mutation、effect 等資料流。

### 範圍

只動 `JobList.tsx` 的結果面板呈現與一個排序 state；候選清單、控制列、MatchCard
內部、求職信、追蹤等不動。

## 無障礙

- `SegmentedControl` 原生可鍵盤操作、選項標籤清楚（「契合度」「最新分析」）。
- 維持既有對比、`:focus-visible`、`prefers-reduced-motion`。

## 驗證計畫

- 後端：跑 pytest 套件（重點 `test_schemas.py`、`test_job_matching.py` 及 match
  repository 相關測試）通過；`set_result` 後讀回的 `JobMatch.analyzed_at` 非空。
- 前端：`cd frontend && npm run build`（`tsc -b && vite build`）通過。
- 手動目視：分析數筆後，切「最新分析」→ 最近完成的在前、pending 置頂；切回
  「契合度」→ 分數由高到低；重整頁面後排序選擇保留。
- 回歸：預設仍為「契合度」、既有舊資料（無 `analyzed_at`）在「最新分析」下殿後而
  非報錯。
