# career-sentinel SP4 — JD × 履歷比對 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 貼一個 104 職缺網址 → curl_cffi 抓完整 JD → 對已存履歷用 LLM 算吻合度(0~100)+ 契合理由 + 缺少技能，web 呈現。

**Architecture:** 新增 `jobfetch.py`（curl_cffi 抓 104 公開詳情 + 純解析）、`match.py`（移植雲端 job_matching，重用 SP3 的 `llm.parse_json`，支援 Foundry）、`models` 加 `JobDetail`/`MatchResult`、`web/app.py` 加 `POST /api/match`（stateless），前端加「JD 比對」分頁。

**Tech Stack:** Python 3.12+、Pydantic v2、curl_cffi、FastAPI、React+Vite+Mantine+TanStack Query。

## Global Constraints

- `sentinel/` 獨立，**不 import/依賴** 雲端 `backend/`、`frontend/`（移植＝複製邏輯）；套件名 `career_sentinel`。
- 抓 JD 用 **curl_cffi**（`impersonate="chrome"`，過 104 TLS 指紋）打 `https://www.104.com.tw/job/ajax/content/{code}`，帶 `Referer: https://www.104.com.tw/job/{code}`。
- 重用 SP3 的 `llm.parse_json`（provider-aware；無 key raise `RuntimeError`）。比對 **stateless**（不存）。
- `JobDetail` 與 `MatchResult` 放 `models.py`。`_MatchReq` 請求 body model 放**模組層級**（FastAPI 無法以閉包內 BaseModel 當 body）。
- API 錯誤：非 104 職缺網址→400「請貼 104 職缺網址」；無履歷→400「請先上傳履歷」（在抓取**之前**檢查、不打網路）；抓取失敗→502「抓取職缺失敗，請確認網址」；無 LLM key（RuntimeError）→400；LLM 失敗→500「比對失敗，請重試」。
- `/api/match` 用 `create_app` 的 `resolved_db` 載履歷；後端只綁 127.0.0.1（沿用）。
- 前端 Tabs 加第三頁「JD 比對」。
- 驗證閘門：`cd sentinel && uv run pytest` 全綠；`cd sentinel/web/frontend && npm run build` 成功。
- Phase 1/2/SP1/SP2/SP3 既有測試不得回歸。

---

### Task 1: `JobDetail` + `MatchResult` 模型

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`
- Test: `sentinel/tests/test_match_models.py`

**Interfaces:**
- Produces：
  - `models.JobDetail(title, company, salary, location, description, work_exp, education, majors: list[str], specialties: list[str])`（全部有預設）
  - `models.MatchResult(score: int, reasons: list[str], gaps: list[str])`

- [ ] **Step 1: 寫失敗測試 `tests/test_match_models.py`**

```python
from career_sentinel.models import JobDetail, MatchResult


def test_jobdetail_defaults():
    jd = JobDetail()
    assert jd.title == "" and jd.majors == [] and jd.specialties == []


def test_matchresult_construct():
    m = MatchResult(score=80, reasons=["熟 Python"], gaps=["缺雲端"])
    assert m.score == 80 and m.reasons == ["熟 Python"] and m.gaps == ["缺雲端"]


def test_matchresult_defaults():
    m = MatchResult()
    assert m.score == 0 and m.reasons == [] and m.gaps == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_match_models.py -v`
Expected: FAIL（`ImportError`）。

- [ ] **Step 3: 在 `models.py` 末尾加兩個模型**

```python
class JobDetail(BaseModel):
    title: str = ""
    company: str = ""
    salary: str = ""
    location: str = ""
    description: str = ""
    work_exp: str = ""
    education: str = ""
    majors: list[str] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_match_models.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: 全測試 + Commit**

Run: `cd sentinel && uv run pytest -q`（全 PASS）
```bash
git add sentinel/src/career_sentinel/models.py sentinel/tests/test_match_models.py
git commit -m "feat(sentinel): JobDetail / MatchResult 模型"
```

---

### Task 2: `jobfetch`（104 JD 抓取）

**Files:**
- Modify: `sentinel/pyproject.toml`（加 `curl_cffi`）
- Create: `sentinel/src/career_sentinel/jobfetch.py`
- Create: `sentinel/tests/fixtures/jd_detail.json`
- Test: `sentinel/tests/test_jobfetch.py`

**Interfaces:**
- Consumes：`models.JobDetail`。
- Produces：`jobfetch.extract_job_code(url) -> str`、`jobfetch.parse_job_detail(payload: dict) -> JobDetail`（純）、`jobfetch.fetch_job_detail(code, *, session=None) -> JobDetail`（curl_cffi；不單測）。

- [ ] **Step 1: 在 `pyproject.toml` 加 `curl_cffi`**

在 `dependencies` 加一行 `"curl_cffi>=0.7",`（保留既有）。

- [ ] **Step 2: 建立去識別化 fixture `tests/fixtures/jd_detail.json`**

（結構取自真實 104 詳情 API；值為去識別化範例）
```json
{
  "data": {
    "header": { "jobName": "全端工程師", "custName": "範例科技有限公司" },
    "jobDetail": {
      "jobDescription": "負責後端 API 設計與前端整合，使用 Python / FastAPI / React，串接 SQL 資料庫。",
      "salary": "月薪 50,000~70,000元",
      "addressRegion": "台北市內湖區"
    },
    "condition": {
      "workExp": "2年以上",
      "edu": "大學",
      "major": ["資訊工程相關"],
      "specialty": [{ "description": "Python" }, { "description": "FastAPI" }, { "description": "SQL" }]
    }
  }
}
```

- [ ] **Step 3: 寫失敗測試 `tests/test_jobfetch.py`**

```python
import json
from pathlib import Path

import pytest

from career_sentinel.jobfetch import extract_job_code, parse_job_detail

FIX = Path(__file__).parent / "fixtures" / "jd_detail.json"


def test_extract_job_code_basic():
    assert extract_job_code("https://www.104.com.tw/job/8pu2t") == "8pu2t"


def test_extract_job_code_with_query_and_slash():
    assert extract_job_code("https://www.104.com.tw/job/8pu2t/?jobsource=index") == "8pu2t"


def test_extract_job_code_non_104_raises():
    with pytest.raises(ValueError):
        extract_job_code("https://example.com/job/123")


def test_parse_job_detail_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    jd = parse_job_detail(data)
    assert jd.title == "全端工程師"
    assert jd.company == "範例科技有限公司"
    assert "FastAPI" in jd.description
    assert jd.salary == "月薪 50,000~70,000元"
    assert jd.work_exp == "2年以上"
    assert jd.education == "大學"
    assert jd.majors == ["資訊工程相關"]
    assert jd.specialties == ["Python", "FastAPI", "SQL"]
```

- [ ] **Step 4: 跑測試確認失敗**

Run: `cd sentinel && uv sync && uv run pytest tests/test_jobfetch.py -v`
Expected: FAIL（`ModuleNotFoundError: career_sentinel.jobfetch`）。

- [ ] **Step 5: 實作 `jobfetch.py`**

```python
from __future__ import annotations

import re

from .models import JobDetail

_DETAIL_URL = "https://www.104.com.tw/job/ajax/content/{code}"
_WARMUP_URL = "https://www.104.com.tw/jobs/search/"
_CODE_RE = re.compile(r"104\.com\.tw/job/([^/?#]+)")


def extract_job_code(url: str) -> str:
    """從 104 職缺網址取 code（/job/{code}）。非 104 職缺網址 raise ValueError。"""
    m = _CODE_RE.search(url or "")
    if not m:
        raise ValueError("請貼 104 職缺網址")
    return m.group(1)


def parse_job_detail(payload: dict) -> JobDetail:
    """把 104 詳情 API 的 JSON 解析成 JobDetail。"""
    data = payload.get("data", {}) or {}
    header = data.get("header", {}) or {}
    jd = data.get("jobDetail", {}) or {}
    cond = data.get("condition", {}) or {}
    return JobDetail(
        title=(header.get("jobName") or "").strip(),
        company=(header.get("custName") or "").strip(),
        salary=jd.get("salary", "") or "",
        location=jd.get("addressRegion", "") or "",
        description=(jd.get("jobDescription") or "").strip(),
        work_exp=cond.get("workExp", "") or "",
        education=cond.get("edu", "") or "",
        majors=list(cond.get("major", []) or []),
        specialties=[s.get("description", "") for s in (cond.get("specialty", []) or [])],
    )


def fetch_job_detail(code: str, *, session=None) -> JobDetail:
    """curl_cffi 抓 104 公開職缺詳情。需真網路、不單測。"""
    from curl_cffi import requests as creq

    owns = session is None
    session = session or creq.Session(impersonate="chrome", timeout=30)
    try:
        if owns:
            session.get(_WARMUP_URL)  # 暖身，取 cookie
        resp = session.get(
            _DETAIL_URL.format(code=code),
            headers={"Referer": f"https://www.104.com.tw/job/{code}"},
        )
        resp.raise_for_status()
        return parse_job_detail(resp.json())
    finally:
        if owns:
            session.close()
```

- [ ] **Step 6: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_jobfetch.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 7: 全測試 + Commit**

Run: `cd sentinel && uv run pytest -q`（全 PASS）
```bash
git add sentinel/pyproject.toml sentinel/uv.lock sentinel/src/career_sentinel/jobfetch.py sentinel/tests/fixtures/jd_detail.json sentinel/tests/test_jobfetch.py
git commit -m "feat(sentinel): jobfetch（curl_cffi 抓 104 公開 JD + 解析）"
```

---

### Task 3: `match`（比對引擎）

**Files:**
- Create: `sentinel/src/career_sentinel/match.py`
- Test: `sentinel/tests/test_match.py`

**Interfaces:**
- Consumes：`llm.parse_json`、`models.{JobDetail,MatchResult}`。
- Produces：`match.build_prompt(resume_text, target_title, jd: JobDetail) -> str`、`match.match(resume_text, target_title, jd, *, client=None) -> MatchResult`。

- [ ] **Step 1: 寫失敗測試 `tests/test_match.py`**

```python
from career_sentinel import llm, match
from career_sentinel.config import LlmSettings
from career_sentinel.models import JobDetail


def test_build_prompt_contains_resume_and_jd():
    jd = JobDetail(title="全端工程師", company="範例", description="需要 Python/FastAPI", specialties=["Python", "FastAPI"])
    p = match.build_prompt("我會 Python", "後端工程師", jd)
    assert "後端工程師" in p
    assert "我會 Python" in p
    assert "Python/FastAPI" in p
    assert "FastAPI" in p


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": '{"score":80,"reasons":["熟 Python"],"gaps":["缺雲端"]}'}}]}


class _FakeClient:
    def post(self, url, **kw):
        return _FakeResp()


def test_match_with_fake_client(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "openai")
    monkeypatch.setattr(llm, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    jd = JobDetail(title="全端工程師", description="Python")
    out = match.match("我會 Python", "後端工程師", jd, client=_FakeClient())
    assert out.score == 80
    assert out.reasons == ["熟 Python"]
    assert out.gaps == ["缺雲端"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_match.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `match.py`**

```python
from __future__ import annotations

from . import llm
from .models import JobDetail, MatchResult

_SYSTEM = "你是一位專業的求職顧問，請客觀評估履歷與職缺的契合度。"


def build_prompt(resume_text: str, target_title: str, jd: JobDetail) -> str:
    return (
        f"求職者目標職位：{target_title}\n"
        f"履歷：\n{resume_text}\n\n"
        f"職缺：{jd.title}（{jd.company}）\n"
        f"職缺需求：\n{jd.description}\n"
        f"工作經驗：{jd.work_exp}　學歷：{jd.education}\n"
        f"技能：{', '.join(jd.specialties)}\n\n"
        "請評估履歷與此職缺的契合度（0~100 分），並列出契合理由與缺少的技能/待補強。\n"
        '只回 JSON，格式 {"score": <0-100 整數>, "reasons": ["..."], "gaps": ["..."]}。'
    )


def match(resume_text: str, target_title: str, jd: JobDetail, *, client=None) -> MatchResult:
    return llm.parse_json(
        build_prompt(resume_text, target_title, jd),
        MatchResult,
        system=_SYSTEM,
        client=client,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_match.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: 全測試 + Commit**

Run: `cd sentinel && uv run pytest -q`（全 PASS）
```bash
git add sentinel/src/career_sentinel/match.py sentinel/tests/test_match.py
git commit -m "feat(sentinel): match（JD×履歷 比對引擎，重用 llm.parse_json）"
```

---

### Task 4: API `POST /api/match`

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_match.py`

**Interfaces:**
- Consumes：`jobfetch.{extract_job_code,fetch_job_detail}`、`match.match`、`store.load_resume`、`models.JobDetail/MatchResult`。
- Produces：`POST /api/match`。

- [ ] **Step 1: 寫失敗測試 `tests/test_web_match.py`**

```python
from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel import store
from career_sentinel.models import JobDetail, MatchResult, ResumeState


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_match_invalid_url_400(tmp_path):
    r = _client(tmp_path).post("/api/match", json={"job_url": "https://example.com/x"})
    assert r.status_code == 400


def test_match_no_resume_400(tmp_path):
    r = _client(tmp_path).post("/api/match", json={"job_url": "https://www.104.com.tw/job/8pu2t"})
    assert r.status_code == 400  # 履歷為空（在抓取前擋下）


def test_match_success(tmp_path, monkeypatch):
    from career_sentinel import jobfetch, match
    monkeypatch.setattr(jobfetch, "fetch_job_detail", lambda code, **kw: JobDetail(title="全端工程師", company="範例", salary="月薪 6 萬", description="Python"))
    monkeypatch.setattr(match, "match", lambda rt, tt, jd, **kw: MatchResult(score=80, reasons=["熟 Python"], gaps=["缺雲端"]))
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_resume(conn, ResumeState(resume_text="我會 Python", target_title="後端工程師"))
    c = _client(tmp_path)
    r = c.post("/api/match", json={"job_url": "https://www.104.com.tw/job/8pu2t"})
    assert r.status_code == 200
    b = r.json()
    assert b["title"] == "全端工程師"
    assert b["company"] == "範例"
    assert b["score"] == 80
    assert b["gaps"] == ["缺雲端"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_match.py -v`
Expected: FAIL（404）。

- [ ] **Step 3: 改 `web/app.py`**

把 `app.py` 頂端的 `from .. import config, diagnosis, diff, digest, resume, store, watch` 改為加入 `jobfetch, match`：
```python
from .. import config, diagnosis, diff, digest, jobfetch, match, resume, store, watch
```

在現有 `_DiagnoseReq` 模組層級類別附近，加一個模組層級請求 body model：
```python
class _MatchReq(BaseModel):
    job_url: str
```

在 `create_app` 內、resume 三個路由之後、`return app`/靜態掛載之前，加：
```python
    @app.post("/api/match")
    def match_job(req: _MatchReq) -> dict:
        conn = _conn()
        try:
            code = jobfetch.extract_job_code(req.job_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        state = store.load_resume(conn)
        if not state.resume_text.strip():
            raise HTTPException(status_code=400, detail="請先上傳履歷")
        try:
            jd = jobfetch.fetch_job_detail(code)
        except Exception:
            raise HTTPException(status_code=502, detail="抓取職缺失敗，請確認網址")
        try:
            result = match.match(state.resume_text, state.target_title or "（未指定）", jd)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="比對失敗，請重試")
        return {
            "title": jd.title, "company": jd.company, "salary": jd.salary,
            "score": result.score, "reasons": result.reasons, "gaps": result.gaps,
        }
```

（路由函式取名 `match_job` 以免與匯入的 `match` 模組同名；`match.match(...)` 呼叫模組的 `match` 函式。`_MatchReq` 必須在模組層級，FastAPI 才認得它是 JSON body。）

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_web_match.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 5: 全測試 + Commit**

Run: `cd sentinel && uv run pytest -q`（全 PASS）
```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_match.py
git commit -m "feat(sentinel): POST /api/match（貼 104 網址→抓 JD→比對）"
```

---

### Task 5: 前端「JD 比對」分頁

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`
- Modify: `sentinel/web/frontend/src/App.tsx`
- Create: `sentinel/web/frontend/src/MatchPage.tsx`

**Interfaces:**
- Consumes：`POST /api/match`、`GET /api/resume`（判斷 has_resume）。
- Produces：可 build 的「JD 比對」分頁。

- [ ] **Step 1: 在 `src/api.ts` 末尾加 match 型別與函式**

```ts
export interface MatchResult {
  title: string;
  company: string;
  salary: string;
  score: number;
  reasons: string[];
  gaps: string[];
}

export async function matchJob(job_url: string): Promise<Response> {
  return fetch("/api/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_url }),
  });
}
```

- [ ] **Step 2: 建立 `src/MatchPage.tsx`**

```tsx
import { Button, Container, List, Progress, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getResume, matchJob, type MatchResult } from "./api";

export default function MatchPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);

  async function run() {
    setErr(null);
    setResult(null);
    setBusy(true);
    const r = await matchJob(url.trim());
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "比對失敗");
      return;
    }
    setResult(await r.json());
  }

  return (
    <Container size="md" py="lg">
      <Title order={2} mb="md">JD 比對</Title>
      {!resume.data?.has_resume && (
        <Text c="orange" mb="sm">請先到「履歷健檢」上傳履歷。</Text>
      )}
      <Stack>
        <TextInput
          label="104 職缺網址"
          placeholder="https://www.104.com.tw/job/xxxxx"
          value={url}
          onChange={(e) => setUrl(e.currentTarget.value)}
        />
        {err && <Text c="red" size="sm">{err}</Text>}
        <Button onClick={run} loading={busy} disabled={!resume.data?.has_resume || !url.trim()}>比對</Button>
        {result && (
          <Stack gap="xs" mt="md">
            <Title order={4}>{result.title}　<Text span c="dimmed" size="sm">{result.company} · {result.salary}</Text></Title>
            <Text>吻合度：{result.score} / 100</Text>
            <Progress value={result.score} />
            <Title order={5} mt="sm">契合理由</Title>
            <List>{result.reasons.map((s, i) => <List.Item key={i}>✓ {s}</List.Item>)}</List>
            <Title order={5} mt="sm">缺少技能 / 待補強</Title>
            <List>{result.gaps.map((g, i) => <List.Item key={i}>! {g}</List.Item>)}</List>
          </Stack>
        )}
      </Stack>
    </Container>
  );
}
```

- [ ] **Step 3: 改 `src/App.tsx` 加第三分頁**

把 `App.tsx` 改為（加入 `MatchPage` import、第三個 Tab 與 Panel）：
```tsx
import { Tabs } from "@mantine/core";
import Dashboard from "./Dashboard";
import MatchPage from "./MatchPage";
import ResumePage from "./ResumePage";

export default function App() {
  return (
    <Tabs defaultValue="dashboard" keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
        <Tabs.Tab value="match">JD 比對</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
      <Tabs.Panel value="match"><MatchPage /></Tabs.Panel>
    </Tabs>
  );
}
```

- [ ] **Step 4: 建置（閘門）**

Run: `cd sentinel/web/frontend && npm run build`
Expected: `tsc -b && vite build` 無型別錯誤、`✓ built`、產出 `dist/`。

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/App.tsx sentinel/web/frontend/src/MatchPage.tsx
git commit -m "feat(sentinel): 前端 JD 比對分頁（貼 104 網址→吻合度+理由+缺口）"
```

---

### Task 6: 真機整合驗證（控制器）

**Files:** 無（驗證任務）

- [ ] **Step 1: 全測試 + 前端建置**

Run: `cd sentinel && uv run pytest -q && cd web/frontend && npm run build`
Expected: pytest 全綠、build 成功。

- [ ] **Step 2: 真機驗證（控制器，serve + httpx）**

`career-sentinel serve` 背景起，然後：
- 先確保有履歷：`POST /api/resume/upload` 一份 txt 履歷（或上傳真實 PDF）。
- `POST /api/match {"job_url": "<真實 104 職缺網址>"}`（`.env` 已設 `FOUNDRY_API_KEY`）→ 預期 200，回 `{title, company, salary, score, reasons, gaps}`，分數 0~100、理由/缺口為真實 LLM 輸出。**這驗證 curl_cffi 抓 JD + Foundry 比對端到端**。
- 非 104 網址 → 400；無履歷時 → 400。
- 若 curl_cffi 抓取失敗（warmup/Referer/TLS）→ 在此暴露、排除（必要時調 `fetch_job_detail`）。
- 驗證後清掉測試用履歷（`save_resume(ResumeState())`）、停 serve。

- [ ] **Step 3: 人工目視（使用者）**

`career-sentinel serve` → 「JD 比對」分頁 → 貼一個你想應徵的 104 職缺網址 → 比對 → 看吻合度/理由/缺口。

- [ ] **Step 4: Commit（里程碑）**

```bash
git commit --allow-empty -m "test(sentinel): SP4 全測試 + 前端建置 + 真機 JD 比對驗證"
```

---

## 完成後

JD 比對可貼 104 網址、抓 JD、對履歷算吻合度+缺口。`jobfetch` 與 `match` 供 SP5（推薦批次比對）重用。見路線圖。
