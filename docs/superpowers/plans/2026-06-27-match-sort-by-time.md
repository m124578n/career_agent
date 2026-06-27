# 職缺分析結果可依分析時間排序 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓職缺契合度頁的分析結果可在「契合度」與「最新分析」兩種排序間切換，並在後端記錄每筆分析完成時間。

**Architecture:** 後端 `JobMatch` schema 新增 `analyzed_at`，於 `MatchRepository.set_result`（狀態轉 done 的唯一蓋點）蓋時間戳，API 同 response model 自動帶出。前端 `JobList` 結果面板加排序切換（`SegmentedControl`），純前端排序：pending 兩模式皆置頂，其餘 done/failed 依模式（契合度→分數；最新→`analyzed_at`）排序。

**Tech Stack:** 後端 Python + FastAPI + Pydantic + Motor/MongoDB（測試用 mongomock-motor + pytest-asyncio）；前端 React 18 + Mantine 7 + TypeScript 5 + Vite 6。

## Global Constraints

- 預設排序為「契合度」（`fit`）；不更動此預設。
- `pending` 在兩種排序模式都置頂（「進行中」即時回饋）；其餘 done/failed 才依模式排序。
- 「最新分析」（`recent`）：done 依 `analyzed_at` 由新到舊，`analyzed_at` 為 null（含舊資料）與 failed 殿後；同層以 `score` 由高到低為次序。
- `analyzed_at` 存 ISO 字串（與 `crawled_at` 一致）；schema 型別 `datetime | None`，前端型別 `string | null`，預設/缺值為 None/null。
- 後端 `MatchRepository.list_by_search` 預設排序維持分數由高到低，不改；不改 API 路由（同一 response model 自動帶出新欄位）。
- 不改分析流程、額度、爬蟲、求職信、其他頁面；前端不改 `matchesQ`/mutation/effect 等資料流。
- 驗證閘門：後端 `cd backend && .venv/Scripts/python.exe -m pytest`（pytest-asyncio，`asyncio_mode=auto`）；前端 `cd frontend && npm run build`（`tsc -b && vite build`）。

---

### Task 1: 後端 `analyzed_at` 時間戳

**Files:**
- Modify: `backend/src/job_tracker/schemas/__init__.py`（`JobMatch`，約第 64-76 行）
- Modify: `backend/src/job_tracker/db/repositories.py`（`MatchRepository.set_result`，約第 101-112 行）
- Test: `backend/tests/test_application_repository.py`（既有檔，追加一個測試函式）

**Interfaces:**
- Consumes：`MatchRepository.set_match/get_match/set_result`（既有）、`JobMatch`、`Job`（既有 schema）。
- Produces：`JobMatch.analyzed_at: datetime | None`（前端 Task 2 對應 `analyzed_at?: string | null`）；`set_result` 後該筆 `analyzed_at` 非空。

- [ ] **Step 1: schema 新增 `analyzed_at` 欄位**

在 `backend/src/job_tracker/schemas/__init__.py` 的 `JobMatch` 內，`relevant` 那行之後新增（`datetime` 已於檔頭 import）：

```python
    status: str = "done"
    relevant: bool = True  # 關鍵字是否命中（廣告→False，前端預設勾選用）
    analyzed_at: datetime | None = None  # 分析完成（status→done）時間；candidate/pending 為 None
```

- [ ] **Step 2: 追加失敗測試**

在 `backend/tests/test_application_repository.py` 檔尾追加：

```python
async def test_set_result_stamps_analyzed_at():
    from job_tracker.db.repositories import MatchRepository
    from job_tracker.schemas import Job, JobMatch
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["test"]
    mr = MatchRepository(db)
    job = Job(job_id="1", code="c1", title="t", company="co",
              url="https://www.104.com.tw/job/c1")
    await mr.set_match("s1", "u1", JobMatch(job=job, status="pending"))
    pending = await mr.get_match("s1", "1")
    assert pending.analyzed_at is None  # 尚未分析

    analysis = JobMatch(job=job, score=80, reasons=["r"], gaps=["g"])
    await mr.set_result("s1", "1", analysis)
    done = await mr.get_match("s1", "1")
    assert done.status == "done"
    assert done.analyzed_at is not None  # done 後蓋上時間戳
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_application_repository.py::test_set_result_stamps_analyzed_at -v`
Expected: FAIL，於 `assert done.analyzed_at is not None`（schema 已有欄位但 `set_result` 尚未蓋值，故為 None）。

- [ ] **Step 4: `set_result` 蓋上時間戳**

在 `backend/src/job_tracker/db/repositories.py` 的 `MatchRepository.set_result` 的 `$set` 字典內加入 `analyzed_at`（`datetime`、`UTC` 已於檔頭 import）：

```python
    async def set_result(self, search_id, job_id, analysis) -> None:
        await self._col.update_one(
            {"_id": f"{search_id}|{job_id}"},
            {"$set": {
                "score": analysis.score,
                "reasons": analysis.reasons,
                "gaps": analysis.gaps,
                "benefits": analysis.benefits,
                "requires_external_apply": analysis.requires_external_apply,
                "status": "done",
                "analyzed_at": datetime.now(UTC).isoformat(),
            }},
        )
```

- [ ] **Step 5: 跑測試確認通過（含全套回歸）**

Run: `cd backend && .venv/Scripts/python.exe -m pytest -q`
Expected: 全數 PASS（含新測試與既有 `test_set_result_writes_benefits` 等）。

- [ ] **Step 6: Commit**

```bash
git add backend/src/job_tracker/schemas/__init__.py backend/src/job_tracker/db/repositories.py backend/tests/test_application_repository.py
git commit -m "feat(matches): 分析完成時蓋 analyzed_at 時間戳"
```

---

### Task 2: 前端排序切換（契合度 / 最新分析）

**Files:**
- Modify: `frontend/src/types/index.ts`（`JobMatch`，約第 40-50 行）
- Modify: `frontend/src/pages/JobList.tsx`

**Interfaces:**
- Consumes：`JobMatch`（含 Task 1 新增、前端對應的 `analyzed_at?: string | null`）；`results`（`JobList()` 內既有，`matches.filter(status !== "candidate")`）；`resultLimit`（既有 state）。
- Produces：無對外匯出。

- [ ] **Step 1: 前端型別新增 `analyzed_at`**

在 `frontend/src/types/index.ts` 的 `JobMatch` 內，`relevant` 之後新增：

```ts
export interface JobMatch {
  job: Job;
  score: number;
  reasons: string[];
  gaps: string[];
  benefits: string[];
  requires_external_apply: boolean;
  cover_letter?: string | null;
  status: "candidate" | "pending" | "done" | "failed";
  relevant: boolean;
  analyzed_at?: string | null;
}
```

- [ ] **Step 2: 補匯入（`useMemo`、`SegmentedControl`）**

在 `frontend/src/pages/JobList.tsx`：
- 把 `import { useEffect, useRef, useState } from "react";` 改為
  `import { useEffect, useMemo, useRef, useState } from "react";`
- 在 `@mantine/core` 具名匯入加入 `SegmentedControl`（插入在既有具名匯入清單中，例如 `MultiSelect` 之後）。

- [ ] **Step 3: 新增排序狀態 key 與持久化**

在檔案上方既有的持久化 key 常數（`KW_KEY` / `AREA_KEY` / `SEL_KEY`）區塊加入：

```ts
const SORT_KEY = "jobtracker.job-sort";
```

在 `JobList()` 內，`resultLimit` 的 `useState` 之後加入排序 state：

```ts
  const [sortMode, setSortMode] = useState<"fit" | "recent">(() =>
    localStorage.getItem(SORT_KEY) === "recent" ? "recent" : "fit"
  );
```

在既有持久化 `useEffect`（寫 `KW_KEY` 等）附近新增：

```ts
  useEffect(() => {
    localStorage.setItem(SORT_KEY, sortMode);
  }, [sortMode]);
```

- [ ] **Step 4: 計算排序後結果**

在 `JobList()` 內、`results` 定義之後加入 `sortedResults`（pending 兩模式皆置頂；其餘依模式排序）：

```ts
  const sortedResults = useMemo(() => {
    const arr = [...results];
    arr.sort((a, b) => {
      // pending（進行中）一律置頂；兩者皆 pending 維持原序
      const pa = a.status === "pending" ? 0 : 1;
      const pb = b.status === "pending" ? 0 : 1;
      if (pa !== pb) return pa - pb;
      if (pa === 0) return 0;
      if (sortMode === "recent") {
        // done 依 analyzed_at 由新到舊；null（含 failed / 舊資料）殿後
        const ta = a.analyzed_at ? Date.parse(a.analyzed_at) : -Infinity;
        const tb = b.analyzed_at ? Date.parse(b.analyzed_at) : -Infinity;
        if (ta !== tb) return tb - ta;
      }
      // 契合度模式，或最新模式的同層次序：分數由高到低
      return b.score - a.score;
    });
    return arr;
  }, [results, sortMode]);
```

- [ ] **Step 5: 結果面板標頭加排序切換，並改用 `sortedResults`**

把結果面板標頭（現行 `<div className="jt-panel-head"><span className="jt-eyebrow">契合度排序{...}</span></div>`）替換為：

```tsx
            <div className="jt-panel-head" style={{ flexWrap: "wrap", rowGap: 8 }}>
              <span className="jt-eyebrow">
                分析結果
                {results.length ? (
                  <>
                    {" · "}
                    <b>{results.length}</b> 筆
                  </>
                ) : null}
              </span>
              {results.length > 0 && (
                <SegmentedControl
                  size="xs"
                  value={sortMode}
                  onChange={(v) => setSortMode(v as "fit" | "recent")}
                  data={[
                    { value: "fit", label: "契合度" },
                    { value: "recent", label: "最新分析" },
                  ]}
                />
              )}
            </div>
```

接著把結果清單的 `results.slice(0, resultLimit).map(...)` 改為 `sortedResults.slice(0, resultLimit).map(...)`（只改這一處迭代來源；「顯示更多」的 `results.length > resultLimit` 判斷與 `results.length - resultLimit` 文字維持用 `results`，因兩者長度相同）。

- [ ] **Step 6: 建置驗證**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` 無型別錯誤、`✓ built` 成功。

- [ ] **Step 7: 手動目視**

`/jobs` 分析數筆後：
- 結果面板標頭出現「契合度／最新分析」切換，預設「契合度」（分數由高到低）。
- 切「最新分析」→ 最近完成的在前；剛按「分析選中」時 pending 置頂（兩模式皆是）。
- 重整頁面後排序選擇保留（localStorage）。
- 舊資料（無 `analyzed_at`）在「最新分析」下殿後、不報錯。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/pages/JobList.tsx
git commit -m "feat(jobs): 分析結果可切換契合度/最新分析排序（pending 置頂）"
```

---

## 完成後

兩任務完成後即達成此功能。最終由 subagent-driven 全分支 review 把關，再以 finishing-a-development-branch 決定合併/推送。
