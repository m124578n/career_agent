# career-sentinel 站內關鍵字職缺搜尋 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新「職缺搜尋」分頁：輸入關鍵字（預設帶入關注關鍵字）→ curl_cffi 爬 104 公開搜尋 API → 列出職缺 → 逐筆對履歷比對（重用 SP4/SP5）。

**Architecture:** 新增 `scraper/search.py`（`fetch_search` 用 curl_cffi 打公開搜尋 API；`parse_search` 委派 SP5 `parse_recommendations`，因搜尋結果職缺結構與推薦完全相同）。`GET /api/search?kw=` 回清單並用 `watch.is_watched` 標記。前端把 SP5 推薦分頁的 `JobRow` 抽成共用元件，搜尋分頁重用。

**Tech Stack:** Python 3.12 / Pydantic v2 / curl_cffi（Chrome TLS 指紋，公開資料、不需登入）/ FastAPI / React 18 + Vite + Mantine 7 + TanStack Query。

## Global Constraints

- 搜尋端點（實機擷取確認）：`GET https://www.104.com.tw/jobs/search/api/jobs?keyword=<kw>&page=1&pagesize=20&order=15&asc=0&mode=s`，**公開**（curl_cffi impersonate chrome 可打，200，不需登入）；帶 `Referer: https://www.104.com.tw/jobs/search/?keyword=<kw>`，先 warmup `https://www.104.com.tw/jobs/search/`。`keyword` 需 URL-encode。
- 搜尋回應結構（實機確認）：`{"data": [job...], "metadata": {"pagination": {...}}}`，**單筆 job 欄位與 SP5 推薦完全相同**（`jobNo`/`jobName`/`custName`/`salaryLow`/`salaryHigh`/`s10`/`link.job`）→ `parse_search` 直接委派 `parse_recommendations`。（註：搜尋的 `jobNo` 是長數字、`link.job` 帶短 code；`parse_recommendations` 以 `jobNo`→code、`link.job`→url，比對走 url 的短 code，正確。）
- 只吃**關鍵字**；進階篩選/全分頁/持久化留後。stateless、不存 DB。後端只綁 127.0.0.1。
- 比對重用既有 `POST /api/match`（不改）。
- 既有 115 測試不得回歸。前端須 `npm run build` 通過。
- pytest / npm 從對應目錄執行：後端 `cd sentinel && uv run pytest`；前端 `cd sentinel/web/frontend && npm run build`。

---

### Task 1: `scraper/search.py` — 關鍵字搜尋 + 解析

**Files:**
- Create: `sentinel/src/career_sentinel/scraper/search.py`
- Create: `sentinel/tests/fixtures/search.json`（去識別化）
- Create: `sentinel/tests/test_search.py`

**Interfaces:**
- Consumes: SP5 `scraper.recommend.parse_recommendations`、既有 `RecommendedJob`。
- Produces: `SEARCH_URL: str`、`parse_search(payload: dict) -> list[RecommendedJob]`（純，委派 `parse_recommendations`）、`fetch_search(keyword: str, *, session=None) -> list[RecommendedJob]`（curl_cffi；需真網路、不單測）。

- [ ] **Step 1: 建去識別化 fixture**

Create `sentinel/tests/fixtures/search.json`（jobNo 用長數字、link 帶短 code，驗證 code=jobNo、url=link.job 分離）：

```json
{
  "data": [
    {
      "jobNo": "14221079",
      "jobName": "資料軟體工程師",
      "custName": "範例數據股份有限公司",
      "custNo": "c1d2e3",
      "salaryLow": 43000,
      "salaryHigh": 47000,
      "s10": 50,
      "link": { "job": "https://www.104.com.tw/job/8gt1z", "cust": "https://www.104.com.tw/company/c1d2e3" }
    },
    {
      "jobNo": "12345678",
      "jobName": "後端工程師 Python",
      "custName": "範例雲端有限公司",
      "custNo": "f4g5h6",
      "salaryLow": 60000,
      "salaryHigh": 9999999,
      "s10": 50,
      "link": { "job": "https://www.104.com.tw/job/9xk2p", "cust": "https://www.104.com.tw/company/f4g5h6" }
    }
  ],
  "metadata": { "pagination": { "count": 2, "total": 2, "currentPage": 1, "lastPage": 1 } }
}
```

- [ ] **Step 2: 寫解析失敗測試**

Create `sentinel/tests/test_search.py`：

```python
import json
from pathlib import Path

from career_sentinel.scraper.search import parse_search

FIX = Path(__file__).parent / "fixtures" / "search.json"


def test_parse_search_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    jobs = parse_search(data)
    assert len(jobs) == 2
    j = jobs[0]
    assert j.code == "14221079"                              # jobNo
    assert j.url == "https://www.104.com.tw/job/8gt1z"       # link.job（短 code）
    assert j.title == "資料軟體工程師"
    assert j.company == "範例數據股份有限公司"
    assert j.salary == "月薪 43,000~47,000 元"
    assert j.is_watched is False
    assert jobs[1].salary == "月薪 60,000 元以上"             # salaryHigh=9999999


def test_parse_search_empty():
    assert parse_search({"data": []}) == []
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_search.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.scraper.search）

- [ ] **Step 4: 實作 `scraper/search.py`**

Create `sentinel/src/career_sentinel/scraper/search.py`：

```python
from __future__ import annotations

from urllib.parse import quote

from ..models import RecommendedJob
from .recommend import parse_recommendations

SEARCH_URL = "https://www.104.com.tw/jobs/search/api/jobs?keyword={kw}&page=1&pagesize=20&order=15&asc=0&mode=s"
_WARMUP_URL = "https://www.104.com.tw/jobs/search/"


def parse_search(payload: dict) -> list[RecommendedJob]:
    """搜尋結果職缺結構與推薦完全相同，委派 parse_recommendations。"""
    return parse_recommendations(payload)


def fetch_search(keyword: str, *, session=None) -> list[RecommendedJob]:
    """curl_cffi 打 104 公開職缺搜尋 API。公開資料、不需登入。需真網路、不單測。"""
    from curl_cffi import requests as creq

    owns = session is None
    session = session or creq.Session(impersonate="chrome", timeout=30)
    try:
        kw = quote(keyword)
        if owns:
            session.get(_WARMUP_URL)  # 暖身取 cookie
        resp = session.get(
            SEARCH_URL.format(kw=kw),
            headers={"Referer": f"https://www.104.com.tw/jobs/search/?keyword={kw}"},
        )
        resp.raise_for_status()
        return parse_search(resp.json())
    finally:
        if owns:
            session.close()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_search.py -q`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
cd sentinel && git add src/career_sentinel/scraper/search.py tests/fixtures/search.json tests/test_search.py
git commit -m "feat(sentinel): 關鍵字搜尋 scraper/search（curl_cffi 打公開搜尋 API，解析委派推薦）"
```

---

### Task 2: `GET /api/search` 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_search.py`

**Interfaces:**
- Consumes: `scraper.search.fetch_search`（Task 1）、既有 `watch.is_watched`、`store.load_settings`。
- Produces: `GET /api/search?kw=<keyword>` → `{"jobs": [{code,url,title,company,salary,is_watched}...]}`；空 kw 400；搜尋失敗 502。

- [ ] **Step 1: 寫 API 失敗測試**

Create `sentinel/tests/test_web_search.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel.models import RecommendedJob
from career_sentinel.scraper import search as srch
from career_sentinel.web.app import create_app


def _client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def test_search_ok_marks_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(srch, "fetch_search", lambda kw: [
        RecommendedJob(code="1", url="https://www.104.com.tw/job/aa", title="Python 工程師", company="關注甲公司", salary="月薪 60,000~90,000 元"),
        RecommendedJob(code="2", url="https://www.104.com.tw/job/bb", title="前端工程師", company="其他公司", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": ["關注甲公司"], "watched_keywords": [], "notify_time": None})
    r = client.get("/api/search", params={"kw": "Python"})
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["is_watched"] is True
    assert jobs[1]["is_watched"] is False


def test_search_keyword_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(srch, "fetch_search", lambda kw: [
        RecommendedJob(code="1", url="u", title="資深 Python 工程師", company="甲", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": [], "watched_keywords": ["python"], "notify_time": None})
    r = client.get("/api/search", params={"kw": "工程師"})
    assert r.json()["jobs"][0]["is_watched"] is True


def test_search_empty_keyword_400(tmp_path):
    r = _client(tmp_path).get("/api/search", params={"kw": "  "})
    assert r.status_code == 400


def test_search_missing_keyword_400(tmp_path):
    r = _client(tmp_path).get("/api/search")
    assert r.status_code == 400


def test_search_fetch_error_502(monkeypatch, tmp_path):
    def _boom(kw):
        raise RuntimeError("search HTTP 500")
    monkeypatch.setattr(srch, "fetch_search", _boom)
    r = _client(tmp_path).get("/api/search", params={"kw": "Python"})
    assert r.status_code == 502
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_search.py -q`
Expected: FAIL（/api/search 404）

- [ ] **Step 3: 加路由**

在 `web/app.py` 的 `match_job` 路由之後、`dist = ...` 之前，加：

```python
    @app.get("/api/search")
    def search(kw: str = "") -> dict:
        from ..scraper.search import fetch_search
        if not kw.strip():
            raise HTTPException(status_code=400, detail="請輸入搜尋關鍵字")
        try:
            jobs = fetch_search(kw.strip())
        except Exception:
            raise HTTPException(status_code=502, detail="搜尋失敗，請重試")
        settings = store.load_settings(_conn())
        return {
            "jobs": [
                {
                    "code": j.code, "url": j.url, "title": j.title,
                    "company": j.company, "salary": j.salary,
                    "is_watched": watch.is_watched(j.company, j.title, settings),
                }
                for j in jobs
            ]
        }
```

註：`kw` 是 query 參數（`GET /api/search?kw=`）；延遲 import `fetch_search` 使測試 monkeypatch `scraper.search.fetch_search` 生效、且避免 import 期載入 curl_cffi。

- [ ] **Step 4: 跑測試確認通過 + 全測試無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/web/app.py tests/test_web_search.py
git commit -m "feat(sentinel): GET /api/search（關鍵字搜尋 + 關注標記）"
```

---

### Task 3: 前端抽共用 `JobRow` 元件 + `searchJobs` api

**Files:**
- Create: `sentinel/web/frontend/src/JobRow.tsx`
- Modify: `sentinel/web/frontend/src/RecommendPage.tsx`（改用共用 JobRow）
- Modify: `sentinel/web/frontend/src/api.ts`（加 `searchJobs`）

**Interfaces:**
- Consumes: 既有 `matchJob`、`MatchResult`、`RecommendedJob`。
- Produces: 共用 `JobRow`（`export default function JobRow({ job, canMatch })`）；`searchJobs(kw: string) -> Promise<Response>`。供 Task 4 使用。

- [ ] **Step 1: 抽出 `JobRow.tsx`**

Create `sentinel/web/frontend/src/JobRow.tsx`（內容即 RecommendPage 現有的 JobRow，改為獨立 export）：

```tsx
import { Anchor, Badge, Button, Card, Group, List, Progress, Stack, Text } from "@mantine/core";
import { useState } from "react";
import { matchJob, type MatchResult, type RecommendedJob } from "./api";

export default function JobRow({ job, canMatch }: { job: RecommendedJob; canMatch: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);

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

  return (
    <Card withBorder padding="md">
      <Group justify="space-between" wrap="nowrap">
        <div>
          <Group gap="xs">
            <Text fw={600}>{job.title}</Text>
            {job.is_watched && <Badge color="orange">★關注</Badge>}
          </Group>
          <Text size="sm" c="dimmed">{job.company} · {job.salary}</Text>
        </div>
        <Group gap="xs" wrap="nowrap">
          <Anchor href={job.url} target="_blank" size="sm">去 104 看</Anchor>
          <Button size="xs" onClick={run} loading={busy} disabled={!canMatch}>比對</Button>
        </Group>
      </Group>
      {err && <Text c="red" size="sm" mt="xs">{err}</Text>}
      {result && (
        <Stack gap="xs" mt="sm">
          <Text size="sm">吻合度：{result.score} / 100</Text>
          <Progress value={result.score} />
          <Text size="sm" fw={600}>契合理由</Text>
          <List size="sm">{result.reasons.map((s, i) => <List.Item key={i}>✓ {s}</List.Item>)}</List>
          <Text size="sm" fw={600}>缺少技能 / 待補強</Text>
          <List size="sm">{result.gaps.map((g, i) => <List.Item key={i}>! {g}</List.Item>)}</List>
        </Stack>
      )}
    </Card>
  );
}
```

- [ ] **Step 2: RecommendPage 改用共用 JobRow**

覆寫 `sentinel/web/frontend/src/RecommendPage.tsx`（刪除內部 JobRow，改 import；其餘不變）：

```tsx
import { Button, Container, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getRecommend, getResume, type RecommendedJob } from "./api";
import JobRow from "./JobRow";

export default function RecommendPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [jobs, setJobs] = useState<RecommendedJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canMatch = !!resume.data?.has_resume;

  async function pull() {
    setErr(null);
    setBusy(true);
    const r = await getRecommend();
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "拉取推薦失敗");
      return;
    }
    setJobs((await r.json()).jobs);
  }

  return (
    <Container size="md" py="lg">
      <Title order={2} mb="md">推薦職缺</Title>
      {!canMatch && <Text c="orange" mb="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      <Stack>
        <Button onClick={pull} loading={busy} w="fit-content">
          {busy ? "正在開啟瀏覽器拉取…" : "拉取推薦"}
        </Button>
        {err && <Text c="red" size="sm">{err}</Text>}
        {jobs && jobs.length === 0 && <Text c="dimmed">目前沒有推薦職缺。</Text>}
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
    </Container>
  );
}
```

- [ ] **Step 3: api.ts 加 searchJobs**

在 `sentinel/web/frontend/src/api.ts` 末尾加：

```typescript
export async function searchJobs(kw: string): Promise<Response> {
  return fetch(`/api/search?kw=${encodeURIComponent(kw)}`);
}
```

- [ ] **Step 4: build 確認通過（重構無回歸）**

Run: `cd sentinel/web/frontend && npm run build`
Expected: build 成功、無 TS 錯誤（推薦分頁行為不變）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add web/frontend/src/JobRow.tsx web/frontend/src/RecommendPage.tsx web/frontend/src/api.ts
git commit -m "refactor(sentinel): 抽共用 JobRow 元件 + searchJobs api"
```

---

### Task 4: 前端「職缺搜尋」分頁

**Files:**
- Create: `sentinel/web/frontend/src/SearchPage.tsx`
- Modify: `sentinel/web/frontend/src/App.tsx`（加第五分頁）

**Interfaces:**
- Consumes: `searchJobs`（Task 3）、`JobRow`（Task 3）、既有 `getResume`、`getSettings`、`RecommendedJob`。
- Produces: 「職缺搜尋」分頁 UI。

- [ ] **Step 1: 建 SearchPage.tsx**

Create `sentinel/web/frontend/src/SearchPage.tsx`（搜尋框預設帶入關注關鍵字，可即時改；Enter 或按鈕觸發）：

```tsx
import { Button, Container, Group, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getResume, getSettings, searchJobs, type RecommendedJob } from "./api";
import JobRow from "./JobRow";

export default function SearchPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [kw, setKw] = useState("");
  const [jobs, setJobs] = useState<RecommendedJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [seeded, setSeeded] = useState(false);
  const canMatch = !!resume.data?.has_resume;

  // 首次載入把關注關鍵字帶入搜尋框（只 seed 一次，不覆寫使用者編輯中）
  useEffect(() => {
    if (!seeded && settings.data) {
      setKw((settings.data.watched_keywords ?? []).join(" "));
      setSeeded(true);
    }
  }, [seeded, settings.data]);

  async function run() {
    if (!kw.trim()) return;
    setErr(null);
    setBusy(true);
    const r = await searchJobs(kw.trim());
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "搜尋失敗");
      return;
    }
    setJobs((await r.json()).jobs);
  }

  return (
    <Container size="md" py="lg">
      <Title order={2} mb="md">職缺搜尋</Title>
      {!canMatch && <Text c="orange" mb="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      <Stack>
        <Group>
          <TextInput
            style={{ flex: 1 }}
            placeholder="輸入關鍵字，如 Python 後端"
            value={kw}
            onChange={(e) => setKw(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          />
          <Button onClick={run} loading={busy} disabled={!kw.trim()}>搜尋</Button>
        </Group>
        {err && <Text c="red" size="sm">{err}</Text>}
        {jobs && jobs.length === 0 && <Text c="dimmed">找不到符合的職缺。</Text>}
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
    </Container>
  );
}
```

- [ ] **Step 2: App.tsx 加分頁**

覆寫 `sentinel/web/frontend/src/App.tsx`：

```tsx
import { Tabs } from "@mantine/core";
import Dashboard from "./Dashboard";
import MatchPage from "./MatchPage";
import RecommendPage from "./RecommendPage";
import ResumePage from "./ResumePage";
import SearchPage from "./SearchPage";

export default function App() {
  return (
    <Tabs defaultValue="dashboard" keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
        <Tabs.Tab value="match">JD 比對</Tabs.Tab>
        <Tabs.Tab value="recommend">推薦</Tabs.Tab>
        <Tabs.Tab value="search">職缺搜尋</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
      <Tabs.Panel value="match"><MatchPage /></Tabs.Panel>
      <Tabs.Panel value="recommend"><RecommendPage /></Tabs.Panel>
      <Tabs.Panel value="search"><SearchPage /></Tabs.Panel>
    </Tabs>
  );
}
```

註：此處以 SP5 版 App.tsx（uncontrolled `defaultValue`）為基礎加分頁。若 SP6 已先執行（App 改 controlled），則改在其 controlled 版上加同樣的 `search` Tab 與 Panel。

- [ ] **Step 3: build 確認通過**

Run: `cd sentinel/web/frontend && npm run build`
Expected: build 成功、無 TS 錯誤

- [ ] **Step 4: Commit**

```bash
cd sentinel && git add web/frontend/src/SearchPage.tsx web/frontend/src/App.tsx
git commit -m "feat(sentinel): 前端職缺搜尋分頁（關鍵字搜尋 + 帶入關注詞 + 逐列比對）"
```

---

### Task 5: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`
- Modify: `.superpowers/sdd/progress.md`

- [ ] **Step 1: 真機端到端驗證**

```bash
cd sentinel && uv run career-sentinel serve
```
瀏覽器開儀表板 →「職缺搜尋」分頁 → 搜尋框預設帶入關注關鍵字（若有設）→ 輸入如「Python」→ 按搜尋 → 應看到 104 職缺結果清單（職稱/公司/薪資，關注命中標 ★）→ 對任一筆按「比對」（履歷需先上傳）→ 看到吻合度分數 + 契合理由 + 缺少技能。

- [ ] **Step 2: 全測試最終確認**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 3: 更新 roadmap + ledger、commit**

`docs/superpowers/career-sentinel-roadmap.md`：把 SP-Search 列改為 `| ~~SP-Search~~ | ~~🔎 站內關鍵字職缺搜尋 + 比對~~ | ✅ 已完成（見上） | — |`，在「✅ 已完成」區加一條摘要，並把 review 期 minors（若有）記入技術債區。
`.superpowers/sdd/progress.md`：append 各 Task 完成與真機驗證結果。

```bash
git add docs/superpowers/career-sentinel-roadmap.md .superpowers/sdd/progress.md
git commit -m "docs(sentinel): 站內關鍵字職缺搜尋 完成（roadmap + ledger）"
```

---

## Self-Review

**1. Spec coverage：**
- 關鍵字搜尋 104 公開職缺（curl_cffi）→ Task 1（`fetch_search`）✅
- 解析（重用推薦欄位映射）→ Task 1（`parse_search` 委派 `parse_recommendations`）✅
- `GET /api/search?kw=` + is_watched + 400/502 → Task 2 ✅
- 前端搜尋分頁（帶入關注詞、逐列比對、履歷未上傳禁用）→ Task 4（+ Task 3 共用 JobRow）✅
- 重用 SP5 JobRow → Task 3（抽共用元件）✅
- 重用 SP4 比對（`POST /api/match`）→ Task 3/4（JobRow 用 matchJob）✅
- 只吃關鍵字、stateless、不存 → 全程無 DB 寫入、無篩選 ✅
- 測試（parse/is_watched/API 200·400·502/build/真機）→ Tasks 1·2·4·5 ✅
- 非目標（進階篩選/全分頁/持久化/納排程）→ 未實作，符合 ✅

**2. Placeholder scan：** 無 TBD/TODO；每個 code step 均含完整程式碼。

**3. Type consistency：**
- `parse_search`/`fetch_search`/`SEARCH_URL`（Task 1）與 Task 2 API（延遲 import `fetch_search`）、測試 monkeypatch `search.fetch_search` 一致。
- `RecommendedJob` 欄位（code/url/title/company/salary/is_watched）跨 Task 1 解析、Task 2 序列化、Task 3/4 前端 `JobRow` 一致（重用 SP5 型別）。
- `searchJobs(kw) -> Promise<Response>`（Task 3）與 Task 4 SearchPage 用法（`r.ok` + `(await r.json()).jobs`）一致，與既有 `getRecommend` 同風格。
- 共用 `JobRow`（Task 3 export default）與 Task 4 SearchPage、Task 3 RecommendPage 的 import 一致。
- `watch.is_watched(company, haystack, settings)` 參數順序（`j.company, j.title, settings`）與既有用法一致。

**開放問題解決紀錄（planning 期實機擷取確認）：** 端點 `jobs/search/api/jobs`、公開（curl_cffi 200 不需登入）、`keyword` query + Referer + warmup、回應結構與職缺欄位**與推薦完全相同**（故 `parse_search` 委派 `parse_recommendations`）皆已釘死於 Global Constraints 與 Task 1。
