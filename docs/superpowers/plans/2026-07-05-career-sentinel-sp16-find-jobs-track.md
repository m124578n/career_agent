# SP16：找職缺合一 ＋ 追蹤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 搜尋／推薦／JD 比對 收成一個「找職缺」頁，找到的職缺一鍵追蹤進 SP15 的職缺脊椎，並在求職中心補齊 有興趣／已比對／已客製化 三個狀態群組與排序，讓追蹤的職缺顯示得出來。

**Architecture:** 後端新增追蹤寫入/取消端點（`POST/DELETE /api/tracked`）與貼網址取詳情端點（`GET /api/job`），皆純本地讀寫或只讀 104 詳情；tracked 職缺沿用 SP15 的 `pipeline.build_pipeline` 經 `/api/snapshot` 輸出。前端新增 `FindJobsPage`（SegmentedControl 三來源）取代 Search/Recommend/Match 三頁，`JobRow` 加追蹤鈕，`Dashboard` 補三群組與排序，導覽 4→3。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、SQLite、pytest；React 18 ＋ Vite ＋ Mantine 7 ＋ TanStack Query。

## Global Constraints

- **追蹤/取消是純資料寫入，不碰 104**：`POST/DELETE /api/tracked` 只讀寫本地 SQLite；`GET /api/job` 只讀 104 職缺詳情（既有 `jobfetch.fetch_job_detail`），不寫入 104。
- **tracked_jobs 以 104 code 去重**：重複追蹤同 code = upsert 覆寫、不新增列；保留原 `created_at`；狀態取「較前面」（用 `pipeline.STATE_RANK`）且**不把既有終端狀態 `offer`/`rejected` 降級**（`pipeline.TERMINAL`）。
- **求職中心三群組是前置**：pipeline 早已能產出 `interested`/`matched`/`tailored` 的 PipelineJob，但前端目前只渲染 面試中/已投遞；本 SP 必補 有興趣/已比對/已客製化 三群組，否則追蹤的職缺進了 pipeline 卻不顯示。
- **不得弄丟 SP7 面試功能與 SP15 既有管道**：Dashboard 改動只新增群組/排序/取消追蹤，既有 面試中/已投遞 群組與訊號區行為不變。
- **相容**：`/api/snapshot` 契約不變；`GET /api/search`、`GET /api/recommend`、`POST /api/match`、`POST /api/tailor` 端點不動。
- 時間戳沿用 `datetime.now().isoformat(timespec="seconds")`。後端綁 `127.0.0.1`。前端 `npm run build`（`tsc -b` 於 `noUnusedLocals`）必須過。
- 測試：後端從 `sentinel/` 跑 `python -m pytest`（專案 venv：`sentinel/.venv/Scripts/python.exe`）；前端從 `sentinel/web/frontend` 跑 `npm run build`。

---

### Task 1: 後端追蹤端點 ＋ 貼網址取詳情

**Files:**
- Modify: `sentinel/src/career_sentinel/store.py`（新增 `delete_tracked_job`）
- Modify: `sentinel/src/career_sentinel/web/app.py`（import 補 `datetime`/`TrackedJob`；新增 `_TrackReq`、`POST /api/tracked`、`DELETE /api/tracked/{code}`、`GET /api/job`）
- Test: `sentinel/tests/test_web_tracked.py`（新檔）

**Interfaces:**
- Consumes（皆既有）：`store.get_tracked_job`/`upsert_tracked_job`/`load_settings`、`store.load_tracked_jobs`、`models.TrackedJob`、`pipeline.STATE_RANK`/`pipeline.TERMINAL`、`jobfetch.extract_job_code`（非 104 raise `ValueError`）/`jobfetch.fetch_job_detail`、`watch.is_watched`。
- Produces：
  - `store.delete_tracked_job(conn, code: str) -> None`
  - `POST /api/tracked`（body `_TrackReq`）→ `{"status": "tracked", "state": str}`
  - `DELETE /api/tracked/{code}` → `{"status": "untracked"}`
  - `GET /api/job?url=` → `{"code","url","title","company","salary","is_watched"}`（RecommendedJob 形狀）

- [ ] **Step 1: 寫失敗測試**

建立 `sentinel/tests/test_web_tracked.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel import store
from career_sentinel.web import app as webapp
from career_sentinel.models import TrackedJob


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_track_with_score_sets_matched(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端",
                                     "url": "https://www.104.com.tw/job/abc12", "salary": "6萬", "match_score": 82})
    assert r.status_code == 200
    assert r.json() == {"status": "tracked", "state": "matched"}
    conn = store.connect(tmp_path / "db.sqlite")
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1 and jobs[0].code == "abc12" and jobs[0].state == "matched" and jobs[0].match_score == 82


def test_track_without_score_sets_interested(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端"})
    assert r.json()["state"] == "interested"


def test_track_empty_code_400(tmp_path):
    r = _client(tmp_path).post("/api/tracked", json={"code": "  "})
    assert r.status_code == 400


def test_retrack_same_code_upserts_keeps_created_at(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端"})  # interested
    conn = store.connect(tmp_path / "db.sqlite")
    created0 = store.get_tracked_job(conn, "abc12").created_at
    c.post("/api/tracked", json={"code": "abc12", "match_score": 90})  # → matched
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1  # upsert，不新增
    j = store.get_tracked_job(conn, "abc12")
    assert j.state == "matched" and j.match_score == 90
    assert j.created_at == created0  # created_at 保留
    assert j.company == "甲"  # 舊值在新請求未帶時保留


def test_retrack_does_not_downgrade_terminal(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="offer", created_at="2026-07-01T00:00:00"))
    _client(tmp_path).post("/api/tracked", json={"code": "abc12", "match_score": 70})
    assert store.get_tracked_job(conn, "abc12").state == "offer"  # 不降級


def test_retrack_keeps_furthest_state(tmp_path):
    # 已 matched，再用「無分數（interested）」追蹤 → 維持 matched（取較前面）
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="matched", match_score=80, created_at="2026-07-01T00:00:00"))
    _client(tmp_path).post("/api/tracked", json={"code": "abc12"})
    assert store.get_tracked_job(conn, "abc12").state == "matched"


def test_untrack_removes(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "abc12", "title": "後端"})
    r = c.delete("/api/tracked/abc12")
    assert r.json() == {"status": "untracked"}
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_tracked_jobs(conn) == []


def test_untrack_missing_code_ok(tmp_path):
    r = _client(tmp_path).delete("/api/tracked/nope")
    assert r.status_code == 200  # 不存在也不報錯


def test_get_job_by_url(tmp_path, monkeypatch):
    from career_sentinel import jobfetch
    from career_sentinel.models import JobDetail
    monkeypatch.setattr(jobfetch, "fetch_job_detail",
                        lambda code, **kw: JobDetail(title="後端工程師", company="甲公司", salary="月薪6萬"))
    r = _client(tmp_path).get("/api/job", params={"url": "https://www.104.com.tw/job/abc12"})
    assert r.status_code == 200
    b = r.json()
    assert b["code"] == "abc12" and b["title"] == "後端工程師" and b["company"] == "甲公司" and b["salary"] == "月薪6萬"


def test_get_job_bad_url_400(tmp_path):
    r = _client(tmp_path).get("/api/job", params={"url": "https://example.com/x"})
    assert r.status_code == 400


def test_track_then_snapshot_pipeline_has_matched(tmp_path):
    c = _client(tmp_path)
    c.post("/api/tracked", json={"code": "abc12", "company": "甲", "title": "後端", "match_score": 75})
    body = c.get("/api/snapshot").json()
    states = {j["code"]: j["state"] for j in body["pipeline"]}
    assert states.get("abc12") == "matched"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_tracked.py -v`
Expected: FAIL（`404`/`405` 或 assert 失敗，因端點尚未存在）

- [ ] **Step 3: store 新增 delete**

在 `sentinel/src/career_sentinel/store.py` 結尾（`upsert_tracked_job` 之後）新增：

```python
def delete_tracked_job(conn: sqlite3.Connection, code: str) -> None:
    conn.execute("DELETE FROM tracked_jobs WHERE code = ?", (code,))
    conn.commit()
```

- [ ] **Step 4: app.py import 補齊**

`sentinel/src/career_sentinel/web/app.py`：
- 第 7 行 `from datetime import date` 改為 `from datetime import date, datetime`。
- 第 15 行 `from ..models import ChatMessage, ChatState, ResumeState, Settings, SuggestedUpdate, interview_key` 改為在清單加入 `TrackedJob`：
  `from ..models import ChatMessage, ChatState, ResumeState, Settings, SuggestedUpdate, TrackedJob, interview_key`

- [ ] **Step 5: 新增 `_TrackReq` 與三個端點**

在 `_MatchReq`（約第 26-27 行）附近加入請求模型：

```python
class _TrackReq(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    match_score: int | None = None
```

在 `create_app` 內（與其他 `@app.post`/`@app.get` 端點同層，放在 `/api/match` 或 `/api/tailor` 端點附近）新增：

```python
    @app.post("/api/tracked")
    def track_job(req: _TrackReq) -> dict:
        if not req.code.strip():
            raise HTTPException(status_code=400, detail="缺少職缺代碼")
        conn = _conn()
        now = datetime.now().isoformat(timespec="seconds")
        new_state = "matched" if req.match_score is not None else "interested"
        existing = store.get_tracked_job(conn, req.code)
        if existing is not None:
            created_at = existing.created_at or now
            if existing.state in pipeline.TERMINAL:
                final_state = existing.state
            elif pipeline.STATE_RANK.get(new_state, 0) >= pipeline.STATE_RANK.get(existing.state, 0):
                final_state = new_state
            else:
                final_state = existing.state
            match_score = req.match_score if req.match_score is not None else existing.match_score
            company = req.company or existing.company
            title = req.title or existing.title
            url = req.url or existing.url
            salary = req.salary or existing.salary
        else:
            created_at = now
            final_state = new_state
            match_score = req.match_score
            company, title, url, salary = req.company, req.title, req.url, req.salary
        store.upsert_tracked_job(conn, TrackedJob(
            code=req.code, company=company, title=title, url=url, salary=salary,
            state=final_state, match_score=match_score, created_at=created_at, updated_at=now,
        ))
        return {"status": "tracked", "state": final_state}

    @app.delete("/api/tracked/{code}")
    def untrack_job(code: str) -> dict:
        store.delete_tracked_job(_conn(), code)
        return {"status": "untracked"}

    @app.get("/api/job")
    def job_by_url(url: str = "") -> dict:
        if not url.strip():
            raise HTTPException(status_code=400, detail="請提供職缺網址")
        try:
            code = jobfetch.extract_job_code(url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            jd = jobfetch.fetch_job_detail(code)
        except Exception:
            raise HTTPException(status_code=502, detail="抓取職缺失敗，請確認網址")
        settings = store.load_settings(_conn())
        return {
            "code": code, "url": url, "title": jd.title, "company": jd.company,
            "salary": jd.salary, "is_watched": watch.is_watched(jd.company, jd.title, settings),
        }
```

- [ ] **Step 6: 跑測試確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_tracked.py -v`
Expected: PASS（11 passed）

- [ ] **Step 7: 全測試回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/store.py sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_tracked.py
git commit -m "feat(sentinel): 追蹤端點 /api/tracked + 貼網址 /api/job（SP16）"
```

---

### Task 2: 求職中心補三群組 ＋ 排序 ＋ 取消追蹤（＋ api.ts client）

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（新增 `trackJob`/`untrackJob`/`getJobByUrl`）
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`（補 有興趣/已比對/已客製化 三群組、排序、取消追蹤 ActionIcon）
- 驗證：`sentinel/web/frontend` 下 `npm run build`

**Interfaces:**
- Consumes：`/api/snapshot` 的 `pipeline`（`PipelineJob[]`，SP15）；`/api/tracked`（Task 1）。
- Produces（api.ts，供 Task 3/4 用）：
  - `trackJob(body: {code:string;company?:string;title?:string;url?:string;salary?:string;match_score?:number|null}): Promise<Response>`
  - `untrackJob(code: string): Promise<Response>`
  - `getJobByUrl(url: string): Promise<Response>`

- [ ] **Step 1: api.ts 新增三個 client 函式**

在 `sentinel/web/frontend/src/api.ts` 適當位置（`RecommendedJob` interface 之後）新增：

```typescript
export interface TrackReq {
  code: string;
  company?: string;
  title?: string;
  url?: string;
  salary?: string;
  match_score?: number | null;
}

export async function trackJob(body: TrackReq): Promise<Response> {
  return fetch("/api/tracked", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function untrackJob(code: string): Promise<Response> {
  return fetch(`/api/tracked/${encodeURIComponent(code)}`, { method: "DELETE" });
}

export async function getJobByUrl(url: string): Promise<Response> {
  return fetch(`/api/job?url=${encodeURIComponent(url)}`);
}
```

- [ ] **Step 2: Dashboard 匯入與排序準備**

在 `sentinel/web/frontend/src/Dashboard.tsx`：
- import 補 `untrackJob`（與既有 `dismissInterview` 等同一行 from "./api"）與圖示 `IconX`（from "@tabler/icons-react"）。
- 在既有 `const appliedJobs = ...` 之後，補三個手動群組與排序（面試中/已投遞加排序、三手動群組依分數）：

```typescript
  const interestedJobs = pipe.filter((j) => j.state === "interested");
  const matchedJobs = pipe.filter((j) => j.state === "matched");
  const tailoredJobs = pipe.filter((j) => j.state === "tailored");

  // 排序：面試中依 when、已投遞依 applied_at 升冪；三手動群組依 match_score 降冪（無分數殿後）
  const byWhen = (a: PipelineJob, b: PipelineJob) => (a.when || "").localeCompare(b.when || "");
  const byApplied = (a: PipelineJob, b: PipelineJob) => (a.applied_at || "").localeCompare(b.applied_at || "");
  const byScore = (a: PipelineJob, b: PipelineJob) => (b.match_score ?? -1) - (a.match_score ?? -1);
  const upcomingSorted = [...upcomingJobs].sort(byWhen);
  const appliedSorted = [...appliedJobs].sort(byApplied);
  const matchedSorted = [...matchedJobs].sort(byScore);
  const tailoredSorted = [...tailoredJobs].sort(byScore);

  const untrack = (code: string) => async () => {
    try {
      await untrackJob(code);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { window.alert("網路錯誤，請重試"); }
  };
```

> 把既有職缺管道區塊中面試中用的 `upcomingJobs.map` 改為 `upcomingSorted.map`、已投遞 `appliedJobs.map` 改為 `appliedSorted.map`（僅換排序後的陣列，其餘 JSX 不變）。KPI「即將面試」維持讀 `upcomingJobs.length`（未 dismiss 數，順序不影響長度）。

- [ ] **Step 3: 在職缺管道加三個手動群組**

在既有「已投遞」群組之後（仍在 `sec-pipeline` 那個 `<div>` 內），加入三個群組。每列一個「取消追蹤」ActionIcon：

```tsx
    {tailoredSorted.length > 0 && (
      <>
        <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>已客製化</Text>
        {tailoredSorted.map((j: PipelineJob) => (
          <Row key={j.key}>
            <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
              {j.watched && <Star />}
              <Text size="sm" truncate>
                <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
                <Text span c="dimmed"> · {j.title}</Text>
              </Text>
              <ResearchButton company={j.company} />
            </Group>
            <ActionIcon variant="subtle" color="gray" size="sm" title="取消追蹤" style={{ flexShrink: 0 }}
              onClick={untrack(j.code)}>
              <IconX size={14} />
            </ActionIcon>
          </Row>
        ))}
      </>
    )}

    {matchedSorted.length > 0 && (
      <>
        <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>已比對</Text>
        {matchedSorted.map((j: PipelineJob) => (
          <Row key={j.key}>
            <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
              {j.watched && <Star />}
              <Text size="sm" truncate>
                <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
                <Text span c="dimmed"> · {j.title}</Text>
              </Text>
              {j.match_score != null && <Badge size="sm" variant="light" color="teal">{j.match_score}</Badge>}
              <ResearchButton company={j.company} />
            </Group>
            <ActionIcon variant="subtle" color="gray" size="sm" title="取消追蹤" style={{ flexShrink: 0 }}
              onClick={untrack(j.code)}>
              <IconX size={14} />
            </ActionIcon>
          </Row>
        ))}
      </>
    )}

    {interestedJobs.length > 0 && (
      <>
        <Text size="xs" c="dimmed" mb={6} mt="md" fw={600} style={{ letterSpacing: 1 }}>有興趣</Text>
        {interestedJobs.map((j: PipelineJob) => (
          <Row key={j.key}>
            <Group gap={8} wrap="nowrap" style={{ minWidth: 0, flex: 1 }}>
              {j.watched && <Star />}
              <Text size="sm" truncate>
                <CompanyLink name={j.company} href={j.job_url || j.company_url || undefined} />
                <Text span c="dimmed"> · {j.title}</Text>
              </Text>
              <ResearchButton company={j.company} />
            </Group>
            <ActionIcon variant="subtle" color="gray" size="sm" title="取消追蹤" style={{ flexShrink: 0 }}
              onClick={untrack(j.code)}>
              <IconX size={14} />
            </ActionIcon>
          </Row>
        ))}
      </>
    )}
```

> 群組順序：面試中 → 已投遞 →（新）已客製化 → 已比對 → 有興趣，與既有兩群組同在 `sec-pipeline` 內。外層「有無資料才顯示」的條件（`s && (upcomingJobs.length > 0 || appliedJobs.length > 0 || doneJobs.length > 0)`）要加上三個新群組，改為：`s && (upcomingJobs.length > 0 || appliedJobs.length > 0 || doneJobs.length > 0 || tailoredSorted.length > 0 || matchedSorted.length > 0 || interestedJobs.length > 0)`。

- [ ] **Step 4: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功（無型別/unused 錯誤）。若 `Badge`/`ActionIcon`/`IconX` 未匯入而報錯，補上對應 import（`Badge`/`ActionIcon` 來自 `@mantine/core`、`IconX` 來自 `@tabler/icons-react`）。

- [ ] **Step 5: 後端回歸（確認沒動到後端）**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠。

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/Dashboard.tsx
git commit -m "feat(sentinel): 求職中心補 有興趣/已比對/已客製化 三群組+排序+取消追蹤（SP16）"
```

---

### Task 3: JobRow 加追蹤鈕

**Files:**
- Modify: `sentinel/web/frontend/src/JobRow.tsx`（加 `tracked` prop ＋追蹤/已追蹤 toggle 鈕）
- 驗證：`sentinel/web/frontend` 下 `npm run build`

**Interfaces:**
- Consumes：`trackJob`/`untrackJob`（Task 2 api.ts）；`RecommendedJob`（既有）。
- Produces：`JobRow` 新增必填 prop `tracked: boolean`（呼叫端 `FindJobsPage`（Task 4）依脊椎狀態傳入）。

- [ ] **Step 1: JobRow 加追蹤鈕**

改寫 `sentinel/web/frontend/src/JobRow.tsx`。在既有 import 補 `trackJob`/`untrackJob`；元件簽名加 `tracked` prop；在 `比對` 鈕旁加追蹤 toggle。完整檔如下：

```tsx
import { Anchor, Button, Group, List, Paper, Progress, Stack, Text } from "@mantine/core";
import { IconStarFilled } from "@tabler/icons-react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { matchJob, trackJob, untrackJob, type MatchResult, type RecommendedJob } from "./api";
import BusyHint from "./BusyHint";
import ResearchButton from "./ResearchButton";

export default function JobRow({ job, canMatch, tracked }: { job: RecommendedJob; canMatch: boolean; tracked: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);
  const [trackBusy, setTrackBusy] = useState(false);

  async function run() {
    setErr(null);
    setBusy(true);
    const r = await matchJob(job.url);
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "比對失敗");
      return;
    }
    setResult(await r.json());
  }

  async function toggleTrack() {
    setTrackBusy(true);
    try {
      if (tracked) {
        await untrackJob(job.code);
      } else {
        await trackJob({
          code: job.code, company: job.company, title: job.title,
          url: job.url, salary: job.salary,
          match_score: result ? result.score : null,
        });
      }
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch {
      setErr("網路錯誤，請重試");
    } finally {
      setTrackBusy(false);
    }
  }

  return (
    <Paper bg="dark.6" radius="md" px="md" py={12} className="flat-row" style={{ transition: "background-color 200ms" }}>
      <Group justify="space-between" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            {job.is_watched && (
              <IconStarFilled size={12} style={{ color: "var(--mantine-color-tangerine-5)", flexShrink: 0 }} />
            )}
            <Text fw={600} size="sm" truncate>{job.title}</Text>
            <ResearchButton company={job.company} />
          </Group>
          <Text size="xs" c="dimmed">{job.company} · <Text span c="teal.5" ff="monospace">{job.salary}</Text></Text>
        </div>
        <Group gap="sm" wrap="nowrap">
          <Anchor href={job.url} target="_blank" size="xs" c="dimmed">去 104 看</Anchor>
          <Button size="compact-sm" variant="light" onClick={run} loading={busy} disabled={!canMatch}>比對</Button>
          <Button size="compact-sm" variant={tracked ? "filled" : "outline"} color="teal"
            onClick={toggleTrack} loading={trackBusy}>
            {tracked ? "已追蹤" : "追蹤"}
          </Button>
          <BusyHint active={busy} label="比對中" />
        </Group>
      </Group>
      {err && <Text c="danger.6" size="sm" mt="xs">{err}</Text>}
      {result && (
        <Stack gap={6} mt="sm">
          <Group align="baseline" gap={6}>
            <Text c="teal.5" fw={700} ff="'Space Grotesk', sans-serif" size="xl">{result.score}</Text>
            <Text c="dimmed" size="xs">/ 100</Text>
          </Group>
          <Progress value={result.score} color="teal" size="sm" />
          <Text size="xs" fw={600}>契合理由</Text>
          <List size="xs" spacing={2}>{result.reasons.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
          <Text size="xs" fw={600}>缺少技能 / 待補強</Text>
          <List size="xs" spacing={2}>{result.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
        </Stack>
      )}
    </Paper>
  );
}
```

> 追蹤時若此列已比對過（`result` 有值）帶 `match_score`，後端會設 `matched`；否則 `interested`。已追蹤再按＝取消追蹤。

- [ ] **Step 2: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: **會失敗**——因為既有呼叫端 `SearchPage.tsx`/`RecommendPage.tsx` 用 `<JobRow job=… canMatch=… />` 少了新必填 prop `tracked`。這兩個檔在 Task 4 會被刪除；本任務為了讓 build 綠，暫時在這兩處補 `tracked={false}`（Task 4 刪檔時一併移除）。改完再跑 `npm run build`。
Expected（補上後）: 成功。

> 若你偏好，Task 3 也可只改 JobRow 並容忍 build 暫時紅，交由 Task 4 一次補齊——但本計畫要求每個任務結束時 build 綠，故在此補 `tracked={false}` 於 SearchPage/RecommendPage 的 `<JobRow>`。

- [ ] **Step 3: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（未動後端）。

- [ ] **Step 4: Commit**

```bash
git add sentinel/web/frontend/src/JobRow.tsx sentinel/web/frontend/src/SearchPage.tsx sentinel/web/frontend/src/RecommendPage.tsx
git commit -m "feat(sentinel): JobRow 加追蹤鈕（SP16）"
```

---

### Task 4: FindJobsPage ＋ 導覽收斂 ＋ 移除舊頁

**Files:**
- Create: `sentinel/web/frontend/src/FindJobsPage.tsx`
- Modify: `sentinel/web/frontend/src/Sidebar.tsx`（`PageKey`/`NAV`）
- Modify: `sentinel/web/frontend/src/App.tsx`（掛載 FindJobsPage、移除三頁、橫幅按鈕改指）
- Delete: `sentinel/web/frontend/src/SearchPage.tsx`、`RecommendPage.tsx`、`MatchPage.tsx`
- 驗證：`sentinel/web/frontend` 下 `npm run build`

**Interfaces:**
- Consumes：`searchJobs`/`getRecommend`/`getResume`/`getSettings`/`getSnapshot`/`getJobByUrl`（api.ts）；`JobRow`（Task 3，需傳 `tracked`）；`RecommendedJob`/`PipelineJob`（api.ts 型別）。

- [ ] **Step 1: 建立 FindJobsPage**

建立 `sentinel/web/frontend/src/FindJobsPage.tsx`。三來源 SegmentedControl；tracked 狀態由 `/api/snapshot` 的 pipeline 算出（該 code 是否已在脊椎，且非純 104 訊號——用 tracked 判定：pipeline 內 state 屬於 interested/matched/tailored/offer/rejected 視為已追蹤；但更穩妥是比對 code 是否在 pipeline 且來自 tracked。此處採簡化且正確的判準：凡 pipeline 內存在該 code 即視為「已在脊椎」＝已追蹤，因 applied/interviewing 也算在管道内可取消意義不大——故僅以 tracked 群組 state 判定）：

```tsx
import { Button, Group, SegmentedControl, Stack, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  getJobByUrl, getRecommend, getResume, getSettings, getSnapshot,
  searchJobs, type RecommendedJob,
} from "./api";
import BusyHint from "./BusyHint";
import JobRow from "./JobRow";
import { PageContainer, PageHeader } from "./ui";

const TRACKED_STATES = new Set(["interested", "matched", "tailored", "offer", "rejected"]);

export default function FindJobsPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const canMatch = !!resume.data?.has_resume;

  const [source, setSource] = useState("search");

  // 關鍵字搜尋
  const [kw, setKw] = useState("");
  const [seeded, setSeeded] = useState(false);
  const [searchJobsList, setSearchJobsList] = useState<RecommendedJob[] | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);

  // 推薦
  const [recJobs, setRecJobs] = useState<RecommendedJob[] | null>(null);
  const [recBusy, setRecBusy] = useState(false);
  const [recErr, setRecErr] = useState<string | null>(null);

  // 貼網址
  const [url, setUrl] = useState("");
  const [urlJob, setUrlJob] = useState<RecommendedJob | null>(null);
  const [urlBusy, setUrlBusy] = useState(false);
  const [urlErr, setUrlErr] = useState<string | null>(null);

  useEffect(() => {
    if (!seeded && settings.data) {
      setKw((settings.data.watched_keywords ?? []).join(" "));
      setSeeded(true);
    }
  }, [seeded, settings.data]);

  // 已追蹤的 code 集合（pipeline 內屬於追蹤狀態者）
  const trackedCodes = new Set(
    (snap.data?.pipeline ?? []).filter((j) => TRACKED_STATES.has(j.state)).map((j) => j.code).filter(Boolean),
  );

  async function runSearch() {
    if (!kw.trim()) return;
    setSearchErr(null);
    setSearchBusy(true);
    const r = await searchJobs(kw.trim());
    setSearchBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setSearchErr(b.detail ?? "搜尋失敗");
      return;
    }
    setSearchJobsList((await r.json()).jobs);
  }

  async function runRecommend() {
    setRecErr(null);
    setRecBusy(true);
    const r = await getRecommend();
    setRecBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setRecErr(b.detail ?? "拉取推薦失敗");
      return;
    }
    setRecJobs((await r.json()).jobs);
  }

  async function runUrl() {
    if (!url.trim()) return;
    setUrlErr(null);
    setUrlBusy(true);
    const r = await getJobByUrl(url.trim());
    setUrlBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setUrlErr(b.detail ?? "讀取失敗");
      return;
    }
    setUrlJob(await r.json());
  }

  const rows = (jobs: RecommendedJob[] | null) =>
    jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} tracked={trackedCodes.has(j.code)} />);

  return (
    <PageContainer>
      <Stack gap="md">
        <PageHeader title="找職缺" subtitle="搜尋、推薦或貼網址找職缺，比對後一鍵追蹤" />
        {!canMatch && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
        <SegmentedControl
          value={source}
          onChange={setSource}
          data={[
            { label: "關鍵字搜尋", value: "search" },
            { label: "104 推薦", value: "recommend" },
            { label: "貼網址", value: "url" },
          ]}
        />

        {source === "search" && (
          <>
            <Group wrap="nowrap">
              <TextInput
                style={{ flex: 1 }}
                leftSection={<IconSearch size={15} />}
                placeholder="輸入關鍵字，如 Python 後端"
                value={kw}
                onChange={(e) => setKw(e.currentTarget.value)}
                onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              />
              <Button onClick={runSearch} loading={searchBusy} disabled={!kw.trim()}>搜尋</Button>
            </Group>
            <BusyHint active={searchBusy} label="搜尋中" />
            {searchErr && <Text c="danger.6" size="sm">{searchErr}</Text>}
            {searchJobsList && searchJobsList.length === 0 && <Text c="dimmed" size="sm">找不到符合的職缺。</Text>}
            <Stack gap={6}>{rows(searchJobsList)}</Stack>
          </>
        )}

        {source === "recommend" && (
          <>
            <Button onClick={runRecommend} loading={recBusy} w="fit-content">
              {recBusy ? "正在開啟瀏覽器拉取…" : "拉取 104 推薦"}
            </Button>
            <BusyHint active={recBusy} label="抓取中" />
            {recErr && <Text c="danger.6" size="sm">{recErr}</Text>}
            {recJobs && recJobs.length === 0 && <Text c="dimmed" size="sm">目前沒有推薦職缺。</Text>}
            <Stack gap={6}>{rows(recJobs)}</Stack>
          </>
        )}

        {source === "url" && (
          <>
            <Group wrap="nowrap">
              <TextInput
                style={{ flex: 1 }}
                placeholder="https://www.104.com.tw/job/xxxxx"
                value={url}
                onChange={(e) => setUrl(e.currentTarget.value)}
                onKeyDown={(e) => { if (e.key === "Enter") runUrl(); }}
              />
              <Button onClick={runUrl} loading={urlBusy} disabled={!url.trim()}>讀取</Button>
            </Group>
            <BusyHint active={urlBusy} label="讀取中" />
            {urlErr && <Text c="danger.6" size="sm">{urlErr}</Text>}
            <Stack gap={6}>
              {urlJob && <JobRow key={urlJob.code} job={urlJob} canMatch={canMatch} tracked={trackedCodes.has(urlJob.code)} />}
            </Stack>
          </>
        )}
      </Stack>
    </PageContainer>
  );
}
```

- [ ] **Step 2: Sidebar 導覽收斂**

`sentinel/web/frontend/src/Sidebar.tsx`：
- `PageKey` 型別（第 10 行）移除 `"match" | "recommend" | "search"`、加入 `"jobs"`，變成：
  `export type PageKey = "dashboard" | "resume" | "resume104" | "jobs" | "tailor" | "chat";`
- `NAV` 陣列（第 12-21 行）移除 `match`/`recommend`/`search` 三項，在 `104 履歷` 之後、`客製化` 之前插入：
  `{ key: "jobs", label: "找職缺", icon: IconSearch },`
  （`IconArrowsExchange`/`IconStars` 若不再被使用，從第 2-5 行 import 移除以免 unused；`IconSearch` 保留給找職缺。）

- [ ] **Step 3: App.tsx 掛載 FindJobsPage、移除三頁**

`sentinel/web/frontend/src/App.tsx`：
- 移除 `import MatchPage`、`import RecommendPage`、`import SearchPage`（第 7、9、13 行），新增 `import FindJobsPage from "./FindJobsPage";`。
- 移除這三個 `<div>`（第 108、109、110 行）：`match`/`recommend`/`search`；改成單一：
  `<div style={{ display: page === "jobs" ? undefined : "none" }}><FindJobsPage /></div>`
- `due` 橫幅「也拉推薦」按鈕（第 98 行）`onClick={() => setPage("recommend")}` 改為 `onClick={() => setPage("jobs")}`。

- [ ] **Step 4: 刪除舊頁**

```bash
git rm sentinel/web/frontend/src/SearchPage.tsx sentinel/web/frontend/src/RecommendPage.tsx sentinel/web/frontend/src/MatchPage.tsx
```

- [ ] **Step 5: 型別檢查 ＋ build**

Run（於 `sentinel/web/frontend`）：`npm run build`
Expected: 成功。若報 unused import（如 Sidebar 的 `IconArrowsExchange`/`IconStars`、App 殘留引用），回頭清乾淨。若報找不到已刪除模組，代表仍有殘留 import，清掉。

- [ ] **Step 6: 後端回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠。

- [ ] **Step 7: Commit**

```bash
git add -A sentinel/web/frontend/src/
git commit -m "feat(sentinel): 找職缺頁合一(搜尋/推薦/貼網址)+導覽收斂，移除舊三頁（SP16）"
```

---

## Self-Review 註記（計畫作者）

- **Spec coverage：** 後端追蹤/取消/貼網址(Task1)、求職中心三群組+排序+取消追蹤(Task2)、JobRow 追蹤鈕(Task3)、FindJobsPage 合一+導覽收斂+刪舊頁(Task4) 全覆蓋。
- **狀態機一致：** Task1 的「取較前面、不降級終端」用 `pipeline.STATE_RANK`/`pipeline.TERMINAL`（SP15 已存在），與 spec 一致；有測試覆蓋 downgrade/furthest/dedup。
- **型別一致：** `trackJob`/`untrackJob`/`getJobByUrl`（Task2 定義）→ JobRow(Task3)/FindJobsPage(Task4) 使用；`JobRow` 新增必填 `tracked` prop，Task3 為維持 build 綠先於 SearchPage/RecommendPage 補 `tracked={false}`，Task4 刪這兩檔一併移除——順序自洽。
- **已追蹤判定：** FindJobsPage 用 `/api/snapshot` pipeline 內 state ∈ {interested,matched,tailored,offer,rejected} 的 code 集合判 tracked（applied/interviewing 屬 104 訊號非手動追蹤，不算「可取消追蹤」）。
- **build 綠不中斷：** 每個前端任務結束都要求 `npm run build` 綠；Task3 特別處理了新必填 prop 導致舊呼叫端編譯失敗的過渡。
- **未破壞既有契約：** search/recommend/match/tailor 端點與 /api/snapshot 契約不動；Dashboard 既有面試中/已投遞群組與訊號區僅加排序陣列替換，行為不變。
