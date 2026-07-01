# career-sentinel SP5 工作推薦 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 career-sentinel web 新增「推薦」分頁：拉出 104 個人化推薦職缺清單、標出命中關注的、每筆可單獨按「比對」看吻合度（重用 SP4）。

**Architecture:** 新增登入態讀取器 `scraper/recommend.py`（比照既有 `scraper/viewers.py`：`parse_recommendations` 純函式 + `fetch_recommendations`/`recommend_session` 走真瀏覽器），`GET /api/recommend` 回清單並用 SP2 `watch.is_watched` 標記，前端 `RecommendPage` 逐列重用既有 `POST /api/match`。順手收兩個 SP4 review minor（`MatchResult.score` clamp、`parse_job_detail` specialty 防禦）。

**Tech Stack:** Python 3.12 / Pydantic v2 / rebrowser-playwright（headful 過 Cloudflare）/ FastAPI / React 18 + Vite + Mantine 7 + TanStack Query。

## Global Constraints

- 後端只綁 127.0.0.1；登入態與個人資料只在本機；推薦**不存 DB**（stateless）。
- 推薦端點：`GET https://www.104.com.tw/api/jobs/personal-recommend-jobs?page=1&pageSize=20`，**必須帶 `Referer: https://www.104.com.tw/` header**，且 session 需先導覽 www 首頁取得該 host 的 Cloudflare clearance（實機擷取確認：不帶 Referer 或 clearance 過期 → 403；帶齊 → 200）。
- 推薦 payload 結構（實機擷取確認）：頂層 `{"data": [job...], "metadata": {...}}`；單筆 job 欄位 `jobNo`（code）、`jobName`（職稱）、`custName`（公司）、`link.job`（詳情完整 URL）、`salaryLow`/`salaryHigh`/`s10`（薪資）。
- 薪資編碼（實機確認）：`s10` 10=面議、50=月薪、60=年薪；`salaryHigh==9999999` 表「以上」；`salaryLow==salaryHigh==0` 表面議。
- 逐筆手動比對——**不做批次一鍵比對**；比對沿用既有 `POST /api/match`，本 SP 不改該端點。
- 既有 102 測試不得回歸。前端須 `npm run build` 通過。
- pytest 從 `sentinel/` 執行：`cd sentinel && uv run pytest`。

---

### Task 1: SP4 review-minor 強健化（score clamp + specialty 防禦）

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（`MatchResult` 加 score clamp validator）
- Modify: `sentinel/src/career_sentinel/jobfetch.py:35`（`parse_job_detail` specialty 防禦）
- Test: `sentinel/tests/test_match_models.py`（新增 clamp 測試）、`sentinel/tests/test_jobfetch.py`（新增 specialty 防禦測試）

**Interfaces:**
- Produces: `MatchResult(score:int)` 保證 score 落在 0~100；`parse_job_detail` 對 specialty 含非 dict／空字串不炸、濾除。

- [ ] **Step 1: 寫 score clamp 失敗測試**

在 `sentinel/tests/test_match_models.py` 末尾加：

```python
def test_match_result_score_clamped_high():
    from career_sentinel.models import MatchResult
    assert MatchResult(score=120).score == 100

def test_match_result_score_clamped_low():
    from career_sentinel.models import MatchResult
    assert MatchResult(score=-5).score == 0

def test_match_result_score_from_float_and_garbage():
    from career_sentinel.models import MatchResult
    assert MatchResult(score=85.7).score == 86
    assert MatchResult(score="not a number").score == 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_match_models.py -q`
Expected: FAIL（score=120 得到 120、或 "not a number" 拋 ValidationError）

- [ ] **Step 3: 加 clamp validator**

`models.py` 的 `MatchResult` 改為（`field_validator` 已在檔案頂部 import）：

```python
class MatchResult(BaseModel):
    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, n))
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_match_models.py -q`
Expected: PASS

- [ ] **Step 5: 寫 specialty 防禦失敗測試**

在 `sentinel/tests/test_jobfetch.py` 末尾加：

```python
def test_parse_job_detail_specialty_tolerates_bad_entries():
    from career_sentinel.jobfetch import parse_job_detail
    payload = {"data": {"condition": {"specialty": [
        {"description": "Python"},
        "壞字串",
        {"description": ""},
        {"description": "  Docker  "},
        None,
    ]}}}
    jd = parse_job_detail(payload)
    assert jd.specialties == ["Python", "Docker"]
```

- [ ] **Step 6: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_jobfetch.py::test_parse_job_detail_specialty_tolerates_bad_entries -q`
Expected: FAIL（`"壞字串".get` → AttributeError）

- [ ] **Step 7: 加 specialty 防禦**

`jobfetch.py` 的 `parse_job_detail` 內 `specialties=` 那行（約第 35 行）改為：

```python
        specialties=[
            s.get("description", "").strip()
            for s in (cond.get("specialty", []) or [])
            if isinstance(s, dict) and (s.get("description") or "").strip()
        ],
```

- [ ] **Step 8: 跑全測試確認通過、無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠，含既有 102）

- [ ] **Step 9: Commit**

```bash
cd sentinel && git add src/career_sentinel/models.py src/career_sentinel/jobfetch.py tests/test_match_models.py tests/test_jobfetch.py
git commit -m "harden(sentinel): MatchResult.score clamp 0~100 + parse_job_detail specialty 防禦（SP4 minors）"
```

---

### Task 2: `RecommendedJob` model

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（新增 `RecommendedJob`）
- Test: `sentinel/tests/test_models.py`（新增建構測試）

**Interfaces:**
- Produces: `RecommendedJob(code:str, url:str, title:str="", company:str="", salary:str="", is_watched:bool=False)` — 供 Task 3 解析、Task 4 API 使用。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_models.py` 末尾加：

```python
def test_recommended_job_defaults():
    from career_sentinel.models import RecommendedJob
    j = RecommendedJob(code="aa1bb", url="https://www.104.com.tw/job/aa1bb")
    assert j.code == "aa1bb"
    assert j.title == "" and j.company == "" and j.salary == ""
    assert j.is_watched is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_models.py::test_recommended_job_defaults -q`
Expected: FAIL（ImportError: cannot import name 'RecommendedJob'）

- [ ] **Step 3: 新增 model**

在 `models.py` 末尾加：

```python
class RecommendedJob(BaseModel):
    code: str
    url: str
    title: str = ""
    company: str = ""
    salary: str = ""
    is_watched: bool = False
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_models.py::test_recommended_job_defaults -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add src/career_sentinel/models.py tests/test_models.py
git commit -m "feat(sentinel): RecommendedJob model（SP5）"
```

---

### Task 3: `scraper/recommend.py` — 解析 + 登入態讀取器

**Files:**
- Create: `sentinel/src/career_sentinel/scraper/recommend.py`
- Create: `sentinel/tests/fixtures/recommend.json`（去識別化）
- Create: `sentinel/tests/test_parse_recommend.py`

**Interfaces:**
- Consumes: `RecommendedJob`（Task 2）、`browser.open_context`/`wait_until_ready`/`is_login_url`（既有）。
- Produces: `RECOMMEND_URL:str`、`parse_recommendations(payload:dict)->list[RecommendedJob]`（純）、`fetch_recommendations(page)->list[RecommendedJob]`（真瀏覽器）、`recommend_session()->list[RecommendedJob]|None`（真瀏覽器，未登入回 None）。

- [ ] **Step 1: 建去識別化 fixture**

Create `sentinel/tests/fixtures/recommend.json`（涵蓋月薪範圍／月薪以上／年薪／面議四種薪資）：

```json
{
  "data": [
    {
      "jobNo": "aa1bb",
      "jobName": "資深後端工程師",
      "custName": "範例雲端股份有限公司",
      "custNo": "c1d2e3",
      "salaryLow": 60000,
      "salaryHigh": 90000,
      "s10": 50,
      "link": { "job": "https://www.104.com.tw/job/aa1bb", "cust": "https://www.104.com.tw/company/c1d2e3" }
    },
    {
      "jobNo": "cc3dd",
      "jobName": "資料工程師",
      "custName": "範例數據科技有限公司",
      "custNo": "f4g5h6",
      "salaryLow": 55000,
      "salaryHigh": 9999999,
      "s10": 50,
      "link": { "job": "https://www.104.com.tw/job/cc3dd", "cust": "https://www.104.com.tw/company/f4g5h6" }
    },
    {
      "jobNo": "ee5ff",
      "jobName": "AI 技術主管",
      "custName": "範例智慧股份有限公司",
      "custNo": "i7j8k9",
      "salaryLow": 1500000,
      "salaryHigh": 2500000,
      "s10": 60,
      "link": { "job": "https://www.104.com.tw/job/ee5ff", "cust": "https://www.104.com.tw/company/i7j8k9" }
    },
    {
      "jobNo": "gg7hh",
      "jobName": "前端工程師",
      "custName": "範例軟體有限公司",
      "custNo": "l1m2n3",
      "salaryLow": 0,
      "salaryHigh": 0,
      "s10": 10,
      "link": { "job": "https://www.104.com.tw/job/gg7hh", "cust": "https://www.104.com.tw/company/l1m2n3" }
    }
  ],
  "metadata": { "pagination": { "count": 4, "total": 4, "currentPage": 1, "lastPage": 1 } }
}
```

- [ ] **Step 2: 寫解析失敗測試**

Create `sentinel/tests/test_parse_recommend.py`：

```python
import json
from pathlib import Path

from career_sentinel.scraper.recommend import parse_recommendations

FIX = Path(__file__).parent / "fixtures" / "recommend.json"


def test_parse_recommend_maps_fields_and_salary():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    jobs = parse_recommendations(data)
    assert len(jobs) == 4
    j = jobs[0]
    assert j.code == "aa1bb"
    assert j.url == "https://www.104.com.tw/job/aa1bb"
    assert j.title == "資深後端工程師"
    assert j.company == "範例雲端股份有限公司"
    assert j.salary == "月薪 60,000~90,000 元"
    assert j.is_watched is False
    assert jobs[1].salary == "月薪 55,000 元以上"   # salaryHigh=9999999
    assert jobs[2].salary == "年薪 1,500,000~2,500,000 元"  # s10=60
    assert jobs[3].salary == "面議"                 # s10=10


def test_parse_recommend_skips_bad_entries():
    payload = {"data": [
        {"jobName": "沒有 jobNo"},                       # 缺 code → 略過
        "壞字串",                                         # 非 dict → 略過
        {"jobNo": "zz9yy", "jobName": "好職缺", "custName": "甲公司",
         "salaryLow": 40000, "salaryHigh": 50000, "s10": 50},  # 無 link → 用 code 組 url
    ]}
    jobs = parse_recommendations(payload)
    assert len(jobs) == 1
    assert jobs[0].code == "zz9yy"
    assert jobs[0].url == "https://www.104.com.tw/job/zz9yy"


def test_parse_recommend_empty():
    assert parse_recommendations({"data": []}) == []
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_parse_recommend.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.scraper.recommend）

- [ ] **Step 4: 實作 `scraper/recommend.py`**

Create `sentinel/src/career_sentinel/scraper/recommend.py`：

```python
from __future__ import annotations

from ..models import RecommendedJob

RECOMMEND_URL = "https://www.104.com.tw/api/jobs/personal-recommend-jobs?page=1&pageSize=20"
_HOME = "https://www.104.com.tw/"
_PERIOD = {40: "時薪", 50: "月薪", 60: "年薪"}


def _format_salary(job: dict) -> str:
    low = job.get("salaryLow") or 0
    high = job.get("salaryHigh") or 0
    if job.get("s10") == 10 or (not low and not high):
        return "面議"
    period = _PERIOD.get(job.get("s10"), "月薪")
    if high >= 9999999:
        return f"{period} {low:,} 元以上"
    return f"{period} {low:,}~{high:,} 元"


def parse_recommendations(payload: dict) -> list[RecommendedJob]:
    """把推薦端點 JSON 解析成 RecommendedJob；壞筆（非 dict／缺 jobNo）略過、不炸整批。"""
    out: list[RecommendedJob] = []
    for job in payload.get("data", []) or []:
        if not isinstance(job, dict):
            continue
        code = (job.get("jobNo") or "").strip()
        if not code:
            continue
        link = job.get("link")
        url = (link.get("job") if isinstance(link, dict) else None) or f"https://www.104.com.tw/job/{code}"
        out.append(
            RecommendedJob(
                code=code,
                url=url,
                title=(job.get("jobName") or "").strip(),
                company=(job.get("custName") or "").strip(),
                salary=_format_salary(job),
            )
        )
    return out


def fetch_recommendations(page) -> list[RecommendedJob]:
    """需已登入且已取得 www host 的 Cloudflare clearance。需帶 Referer。需真瀏覽器、不單測。"""
    resp = page.request.get(RECOMMEND_URL, headers={"Referer": _HOME})
    if not resp.ok:
        raise RuntimeError(f"recommend HTTP {resp.status}")
    return parse_recommendations(resp.json())


def recommend_session() -> list[RecommendedJob] | None:
    """開 headful context → 導覽 www 首頁取得 clearance + 確認登入 → 抓推薦。

    未登入回 None（呼叫端提示先 login）。需真瀏覽器、不單測。
    """
    from rebrowser_playwright.sync_api import sync_playwright

    from .. import browser

    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(_HOME, wait_until="domcontentloaded")
            browser.wait_until_ready(page)
            if browser.is_login_url(page.url):
                return None
            return fetch_recommendations(page)
        finally:
            ctx.close()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_parse_recommend.py -q`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
cd sentinel && git add src/career_sentinel/scraper/recommend.py tests/fixtures/recommend.json tests/test_parse_recommend.py
git commit -m "feat(sentinel): 推薦讀取器 scraper/recommend（解析+登入態抓取）（SP5）"
```

---

### Task 4: `GET /api/recommend` 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`（新增路由）
- Test: `sentinel/tests/test_web_recommend.py`

**Interfaces:**
- Consumes: `scraper.recommend.recommend_session`（Task 3）、`watch.is_watched(company, haystack, settings)`、`store.load_settings`（既有）。
- Produces: `GET /api/recommend` → `{"jobs": [{code,url,title,company,salary,is_watched}...]}`；未登入 409；抓取/解析失敗 502。

- [ ] **Step 1: 寫 API 失敗測試**

Create `sentinel/tests/test_web_recommend.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel.models import RecommendedJob
from career_sentinel.scraper import recommend as rec
from career_sentinel.web.app import create_app


def _client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def test_recommend_ok_marks_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "recommend_session", lambda: [
        RecommendedJob(code="aa1bb", url="https://www.104.com.tw/job/aa1bb",
                       title="後端工程師", company="關注甲公司", salary="月薪 60,000~90,000 元"),
        RecommendedJob(code="cc3dd", url="https://www.104.com.tw/job/cc3dd",
                       title="前端工程師", company="其他公司", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": ["關注甲公司"], "watched_keywords": [], "notify_time": None})
    r = client.get("/api/recommend")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["code"] == "aa1bb" and jobs[0]["is_watched"] is True
    assert jobs[0]["salary"] == "月薪 60,000~90,000 元"
    assert jobs[1]["is_watched"] is False


def test_recommend_keyword_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "recommend_session", lambda: [
        RecommendedJob(code="aa1bb", url="u", title="資深 Python 工程師", company="甲", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": [], "watched_keywords": ["python"], "notify_time": None})
    r = client.get("/api/recommend")
    assert r.json()["jobs"][0]["is_watched"] is True


def test_recommend_not_logged_in_409(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "recommend_session", lambda: None)
    r = _client(tmp_path).get("/api/recommend")
    assert r.status_code == 409


def test_recommend_fetch_error_502(monkeypatch, tmp_path):
    def _boom():
        raise RuntimeError("recommend HTTP 403")
    monkeypatch.setattr(rec, "recommend_session", _boom)
    r = _client(tmp_path).get("/api/recommend")
    assert r.status_code == 502
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_recommend.py -q`
Expected: FAIL（404，路由尚未存在）

- [ ] **Step 3: 加路由**

在 `web/app.py` 的 `match_job` 路由之後、`dist = ...` 之前，加：

```python
    @app.get("/api/recommend")
    def recommend() -> dict:
        from ..scraper.recommend import recommend_session
        try:
            jobs = recommend_session()
        except Exception:
            raise HTTPException(status_code=502, detail="拉取推薦失敗，請重試")
        if jobs is None:
            raise HTTPException(status_code=409, detail="尚未登入，請先在終端機執行：career-sentinel login")
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

註：路由內用 `from ..scraper.recommend import recommend_session` 延遲載入——測試 monkeypatch `scraper.recommend.recommend_session` 後，每次呼叫都重新取該模組屬性，故 patch 生效；且避免 import 期即載入 rebrowser。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_web_recommend.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 跑全後端測試確認無回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 6: Commit**

```bash
cd sentinel && git add src/career_sentinel/web/app.py tests/test_web_recommend.py
git commit -m "feat(sentinel): GET /api/recommend（推薦清單+關注標記）（SP5）"
```

---

### Task 5: 前端「推薦」分頁

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（`RecommendedJob` 型別 + `getRecommend`）
- Create: `sentinel/web/frontend/src/RecommendPage.tsx`
- Modify: `sentinel/web/frontend/src/App.tsx`（加第四分頁）

**Interfaces:**
- Consumes: `GET /api/recommend`、既有 `matchJob(job_url)`、`getResume`、`MatchResult` 型別。
- Produces: 「推薦」分頁 UI。

- [ ] **Step 1: api.ts 加型別與函式**

在 `sentinel/web/frontend/src/api.ts` 末尾加：

```typescript
export interface RecommendedJob {
  code: string;
  url: string;
  title: string;
  company: string;
  salary: string;
  is_watched: boolean;
}

export async function getRecommend(): Promise<Response> {
  return fetch("/api/recommend");
}
```

- [ ] **Step 2: 建 RecommendPage.tsx**

Create `sentinel/web/frontend/src/RecommendPage.tsx`：

```tsx
import { Anchor, Badge, Button, Card, Container, Group, List, Progress, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getRecommend, getResume, matchJob, type MatchResult, type RecommendedJob } from "./api";

function JobRow({ job, canMatch }: { job: RecommendedJob; canMatch: boolean }) {
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

- [ ] **Step 3: App.tsx 加分頁**

改 `sentinel/web/frontend/src/App.tsx`：

```tsx
import { Tabs } from "@mantine/core";
import Dashboard from "./Dashboard";
import MatchPage from "./MatchPage";
import RecommendPage from "./RecommendPage";
import ResumePage from "./ResumePage";

export default function App() {
  return (
    <Tabs defaultValue="dashboard" keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
        <Tabs.Tab value="match">JD 比對</Tabs.Tab>
        <Tabs.Tab value="recommend">推薦</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
      <Tabs.Panel value="match"><MatchPage /></Tabs.Panel>
      <Tabs.Panel value="recommend"><RecommendPage /></Tabs.Panel>
    </Tabs>
  );
}
```

- [ ] **Step 4: build 確認通過**

Run: `cd sentinel/web/frontend && npm run build`
Expected: build 成功、無 TS 錯誤（產出 dist/）

- [ ] **Step 5: Commit**

```bash
cd sentinel && git add web/frontend/src/api.ts web/frontend/src/RecommendPage.tsx web/frontend/src/App.tsx
git commit -m "feat(sentinel): 前端推薦分頁（拉清單+★關注+逐列比對）（SP5）"
```

---

### Task 6: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`（標 SP5 完成）
- Modify: `.superpowers/sdd/progress.md`（記錄）

- [ ] **Step 1: 真機端到端驗證**

前提：使用者已 `career-sentinel login` 過、且**登入態新鮮**（www host clearance 有效；若 403 請重登入）。

```bash
cd sentinel && uv run career-sentinel serve
```
瀏覽器開 `http://127.0.0.1:8000` →「推薦」分頁 →「拉取推薦」→ 應看到推薦職缺清單（含 ★關注 標記在命中設定的公司/關鍵字上）→ 對任一列按「比對」→ 看到吻合度分數 + 契合理由 + 缺少技能。
（履歷需先在「履歷健檢」上傳過，比對鈕才可用。）

- [ ] **Step 2: 全測試最終確認**

Run: `cd sentinel && uv run pytest -q`
Expected: PASS（全綠）

- [ ] **Step 3: 更新 roadmap + ledger、commit**

`docs/superpowers/career-sentinel-roadmap.md`：把 SP5 表格列改為 `| ~~SP5~~ | ~~💡 工作推薦~~ | ✅ 已完成（見上） | — |`，並在「✅ 已完成」區加一條 SP5 摘要。
`.superpowers/sdd/progress.md`：append SP5 各 Task 完成與真機驗證結果。

```bash
git add docs/superpowers/career-sentinel-roadmap.md .superpowers/sdd/progress.md
git commit -m "docs(sentinel): SP5 工作推薦完成（roadmap + ledger）"
```

---

## Self-Review

**1. Spec coverage：**
- 推薦拉取（登入態、Referer、www clearance）→ Task 3（`recommend_session`/`fetch_recommendations`）✅
- 解析 + 薪資格式化 + 容錯 → Task 3（`parse_recommendations`/`_format_salary`）✅
- `RecommendedJob` 型別 → Task 2 ✅
- `GET /api/recommend` + is_watched + 409/502 → Task 4 ✅
- 前端推薦分頁 + 逐列比對 + 履歷未上傳禁用 → Task 5 ✅
- SP4 minors（score clamp、specialty 防禦）→ Task 1 ✅
- stateless（不存 DB）→ API 不寫 DB，只讀 settings ✅
- 非目標（批次/排序/持久化/全分頁）→ 未實作，符合 ✅
- 測試（parse/is_watched/API 200·409·502/前端 build/真機）→ Tasks 3·4·5·6 ✅

**2. Placeholder scan：** 無 TBD/TODO；每個 code step 均含完整程式。

**3. Type consistency：** `RecommendedJob` 欄位（code/url/title/company/salary/is_watched）在 Task 2 定義、Task 3 建構、Task 4 序列化、Task 5 TS 介面一致；`recommend_session`/`fetch_recommendations`/`parse_recommendations` 名稱跨 Task 3/4 一致；`watch.is_watched(company, haystack, settings)` 參數順序與既有 `app.py` 用法一致（company, title, settings）。

**開放問題解決紀錄（planning 期實機擷取確認）：** 端點 URL、Referer 必要性、www clearance、payload 結構、`s10` 薪資編碼、`link.job`→url 皆已釘死於 Global Constraints 與 Task 3 程式。
