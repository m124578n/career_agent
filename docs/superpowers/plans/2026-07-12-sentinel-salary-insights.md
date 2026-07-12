# 薪資行情分析 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 career-sentinel 加「薪資行情分析」：對關鍵字把 104 搜尋結果薪資聚合成月薪中位數與區間，透過聊天唯讀工具與找職缺頁面板呈現，並可回填期望薪資。

**Architecture:** 在 `RecommendedJob` 解析時保留結構化薪資（low/high/period）；`salary_insights.py` 純函式聚合（換算月薪、時薪/面議排除、中位與分位數）；`GET /api/salary-insights` + 聊天唯讀工具 `salary_insights` + 找職缺頁 `SalaryInsightPanel`。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- 換算月薪：月薪照舊、年薪÷12；**時薪與面議排除**（各自計數）。代表值取 [low,high] 中點（無 high 用 low）。
- 統計欄（median/p25/p75/min/max）在無樣本時為 `None`、`sample=0`。
- 結構化薪資欄位皆有預設（向後相容）；不改既有 search/recommend 輸出（格式化 `salary` 字串對所有真實薪資形態保持一致）、不改 negotiate。
- 聊天 `salary_insights` 為自動執行的唯讀工具（回文字給 LLM、無前端事件；僅 foundry tool-use 迴圈有）。
- 端點唯讀；`kw` 空→400、`pages` clamp 1–5、抓取失敗→502。
- 不接外部薪資站；不做趨勢/地區/年資細分。
- 測試用專案 venv：`./.venv/Scripts/python.exe -m pytest -q`（cwd `sentinel/`）；前端 `cd web/frontend && npm run build`。

---

## 檔案結構

```
src/career_sentinel/
├─ models.py                    # RecommendedJob + salary_low/high/period；+ class SalaryInsight
├─ scraper/recommend.py         # _salary_fields；parse_recommendations 填結構化薪資
├─ salary_insights.py           # 新：compute_salary_insights + salary_insights_for_keyword + _percentile
├─ chat/tools.py                # TOOLS + salary_insights 工具 + _execute_salary_insights
├─ chat/prompt.py               # 系統提示工具段補 salary_insights
└─ web/routers/jobs.py          # + GET /api/salary-insights
web/frontend/src/
├─ api.ts                       # + SalaryInsight 型別 + getSalaryInsights()
├─ SalaryInsightPanel.tsx       # 新：薪資行情面板
└─ FindJobsPage.tsx             # 掛 SalaryInsightPanel
tests/
├─ test_scraper_recommend.py    # 新：parse_recommendations 結構化薪資
├─ test_salary_insights.py      # 新：compute_salary_insights
├─ test_web_salary.py           # 新：端點
└─ test_chat_tools.py           # + salary_insights 工具分派 + 提及
```

---

### Task 1: `RecommendedJob` 結構化薪資 + 解析器

**Files:**
- Modify: `src/career_sentinel/models.py`
- Modify: `src/career_sentinel/scraper/recommend.py`
- Test: `tests/test_scraper_recommend.py`

**Interfaces:**
- Produces: `RecommendedJob.salary_low: int`、`salary_high: int`、`salary_period: str`（皆預設）；`recommend._salary_fields(job) -> tuple[int, int, str]`；`parse_recommendations` 填結構化薪資。

- [ ] **Step 1: 加 RecommendedJob 欄位**

在 `src/career_sentinel/models.py` 的 `class RecommendedJob` 的 `is_watched` 之後加：

```python
    salary_low: int = 0       # 原始下限（依 period 單位）
    salary_high: int = 0      # 原始上限；「以上」開放式或面議為 0
    salary_period: str = ""   # "月薪" / "年薪" / "時薪"；面議為 ""
```

- [ ] **Step 2: 寫失敗測試**

建立 `tests/test_scraper_recommend.py`：

```python
from career_sentinel.scraper.recommend import parse_recommendations


def _payload(jobs):
    return {"data": jobs}


def _job(no, low, high, s10):
    return {"jobNo": no, "jobName": "後端", "custName": "甲",
            "salaryLow": low, "salaryHigh": high, "s10": s10,
            "link": {"job": f"https://www.104.com.tw/job/{no}"}}


def test_parse_structured_salary_monthly_range():
    r = parse_recommendations(_payload([_job("a", 60000, 90000, 50)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (60000, 90000, "月薪")
    assert r.salary == "月薪 60,000~90,000 元"


def test_parse_structured_salary_yearly():
    r = parse_recommendations(_payload([_job("b", 1200000, 1800000, 60)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (1200000, 1800000, "年薪")


def test_parse_structured_salary_open_ended():
    r = parse_recommendations(_payload([_job("c", 60000, 9999999, 50)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (60000, 0, "月薪")
    assert r.salary == "月薪 60,000 元以上"


def test_parse_structured_salary_negotiable():
    r = parse_recommendations(_payload([_job("d", 0, 0, 10)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (0, 0, "")
    assert r.salary == "面議"
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_scraper_recommend.py -q`
Expected: FAIL（`salary_low` 等欄位不存在 / 未填）

- [ ] **Step 4: 加 `_salary_fields` 並改寫 `_format_salary`、填欄位**

在 `src/career_sentinel/scraper/recommend.py`，把 `_format_salary` 換成下列（新增 `_salary_fields`，`_format_salary` 改為委派，對所有真實薪資形態輸出一致）：

```python
def _salary_fields(job: dict) -> tuple[int, int, str]:
    """回 (low, high, period)。面議或無數字→(0, 0, "")；『以上』開放式→high 為 0。"""
    low = int(job.get("salaryLow") or 0)
    high = int(job.get("salaryHigh") or 0)
    if job.get("s10") == 10 or (not low and not high):
        return 0, 0, ""
    period = _PERIOD.get(job.get("s10"), "月薪")
    if high >= 9999999:
        high = 0
    return low, high, period


def _format_salary(job: dict) -> str:
    low, high, period = _salary_fields(job)
    if not period:
        return "面議"
    if high == 0:
        return f"{period} {low:,} 元以上"
    return f"{period} {low:,}~{high:,} 元"
```

在 `parse_recommendations` 建 `RecommendedJob(...)` 處，計算並帶入結構化薪資。把該 append 段改成：

```python
        low, high, period = _salary_fields(job)
        out.append(
            RecommendedJob(
                code=code,
                url=url,
                title=(job.get("jobName") or "").strip(),
                company=(job.get("custName") or "").strip(),
                salary=_format_salary(job),
                salary_low=low, salary_high=high, salary_period=period,
            )
        )
```

- [ ] **Step 5: 跑測試確認通過（含全套回歸）**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 既有全綠 + 4 個新測試通過。

- [ ] **Step 6: Commit**

```bash
git add src/career_sentinel/models.py src/career_sentinel/scraper/recommend.py tests/test_scraper_recommend.py
git commit -m "feat(sentinel): RecommendedJob 保留結構化薪資（low/high/period）"
```

---

### Task 2: 聚合層 `salary_insights.py` + `SalaryInsight` model

**Files:**
- Modify: `src/career_sentinel/models.py`（`SalaryInsight`）
- Create: `src/career_sentinel/salary_insights.py`
- Test: `tests/test_salary_insights.py`

**Interfaces:**
- Consumes: `RecommendedJob`（含結構化薪資）、`scraper.search.fetch_search`。
- Produces: `models.SalaryInsight`；`salary_insights.compute_salary_insights(keyword, jobs) -> SalaryInsight`；`salary_insights.salary_insights_for_keyword(keyword, *, pages=3, session=None) -> SalaryInsight`。

- [ ] **Step 1: 加 `SalaryInsight` model**

在 `src/career_sentinel/models.py`（`RecommendedJob` 之後）加：

```python
class SalaryInsight(BaseModel):
    keyword: str = ""
    sample: int = 0            # 納入統計的職缺數（月/年薪且有數字）
    negotiable: int = 0        # 面議數
    hourly_excluded: int = 0   # 時薪排除數
    median_monthly: int | None = None
    p25_monthly: int | None = None
    p75_monthly: int | None = None
    min_monthly: int | None = None
    max_monthly: int | None = None
```

- [ ] **Step 2: 寫失敗測試**

建立 `tests/test_salary_insights.py`：

```python
from career_sentinel import salary_insights
from career_sentinel.models import RecommendedJob, SalaryInsight


def _job(low, high, period):
    return RecommendedJob(code="x", url="u", salary="", salary_low=low, salary_high=high, salary_period=period)


def test_monthly_and_yearly_normalised():
    jobs = [
        _job(60000, 80000, "月薪"),      # rep 70000
        _job(1200000, 1800000, "年薪"),  # 月 100000~150000 → rep 125000
    ]
    r = salary_insights.compute_salary_insights("後端", jobs)
    assert r.sample == 2
    assert r.min_monthly == 70000 and r.max_monthly == 125000
    assert r.median_monthly == 97500  # (70000+125000)/2 內插


def test_hourly_and_negotiable_excluded_and_counted():
    jobs = [
        _job(50000, 70000, "月薪"),
        _job(200, 250, "時薪"),   # 排除
        _job(0, 0, ""),           # 面議排除
    ]
    r = salary_insights.compute_salary_insights("k", jobs)
    assert r.sample == 1 and r.hourly_excluded == 1 and r.negotiable == 1


def test_open_ended_uses_low():
    r = salary_insights.compute_salary_insights("k", [_job(60000, 0, "月薪")])
    assert r.sample == 1 and r.median_monthly == 60000


def test_empty_sample_returns_none():
    r = salary_insights.compute_salary_insights("k", [_job(0, 0, "")])
    assert r.sample == 0 and r.negotiable == 1
    assert r.median_monthly is None and r.p25_monthly is None
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_salary_insights.py -q`
Expected: FAIL（`career_sentinel.salary_insights` 不存在）

- [ ] **Step 4: 實作 `salary_insights.py`**

建立 `src/career_sentinel/salary_insights.py`：

```python
"""薪資行情聚合：把 104 搜尋結果的薪資換算月薪、聚合成中位數與分位數。純資料、可單測。"""
from __future__ import annotations

from .models import RecommendedJob, SalaryInsight


def _percentile(sorted_vals: list[int], q: float) -> int | None:
    """線性內插百分位。q 為 0–1。空列回 None。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 < len(sorted_vals):
        return int(round(sorted_vals[lo] + (sorted_vals[lo + 1] - sorted_vals[lo]) * frac))
    return sorted_vals[lo]


def compute_salary_insights(keyword: str, jobs: list[RecommendedJob]) -> SalaryInsight:
    reps: list[int] = []
    negotiable = 0
    hourly = 0
    for j in jobs:
        if j.salary_period == "時薪":
            hourly += 1
            continue
        if j.salary_period not in ("月薪", "年薪") or j.salary_low <= 0:
            negotiable += 1
            continue
        ml = j.salary_low if j.salary_period == "月薪" else round(j.salary_low / 12)
        if j.salary_high > 0:
            mh = j.salary_high if j.salary_period == "月薪" else round(j.salary_high / 12)
        else:
            mh = 0
        rep = round((ml + mh) / 2) if mh > 0 else ml
        if rep > 0:
            reps.append(rep)
    if not reps:
        return SalaryInsight(keyword=keyword, sample=0, negotiable=negotiable, hourly_excluded=hourly)
    reps.sort()
    return SalaryInsight(
        keyword=keyword, sample=len(reps), negotiable=negotiable, hourly_excluded=hourly,
        median_monthly=_percentile(reps, 0.5),
        p25_monthly=_percentile(reps, 0.25),
        p75_monthly=_percentile(reps, 0.75),
        min_monthly=reps[0], max_monthly=reps[-1],
    )


def salary_insights_for_keyword(keyword: str, *, pages: int = 3, session=None) -> SalaryInsight:
    """抓 pages 頁 104 搜尋、依 code 去重、聚合。真網路、不單測。"""
    from .scraper.search import fetch_search

    pages = max(1, min(5, pages))
    seen: dict[str, RecommendedJob] = {}
    for p in range(1, pages + 1):
        for j in fetch_search(keyword, page=p, session=session):
            seen.setdefault(j.code, j)
    return compute_salary_insights(keyword, list(seen.values()))
```

- [ ] **Step 5: 跑測試確認通過**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_salary_insights.py -q`
Expected: 4 個測試通過。

- [ ] **Step 6: Commit**

```bash
git add src/career_sentinel/models.py src/career_sentinel/salary_insights.py tests/test_salary_insights.py
git commit -m "feat(sentinel): salary_insights 聚合（月薪換算/中位數/分位數）"
```

---

### Task 3: API 端點 + 前端 api

**Files:**
- Modify: `src/career_sentinel/web/routers/jobs.py`
- Modify: `web/frontend/src/api.ts`
- Test: `tests/test_web_salary.py`

**Interfaces:**
- Consumes: `salary_insights.salary_insights_for_keyword`。
- Produces: `GET /api/salary-insights?kw=&pages=3`；前端 `SalaryInsight` 型別、`getSalaryInsights(kw)`。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_web_salary.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel import salary_insights
from career_sentinel.models import SalaryInsight
from career_sentinel.web.app import create_app


def test_salary_endpoint_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(salary_insights, "salary_insights_for_keyword",
                        lambda kw, **kw2: SalaryInsight(keyword=kw, sample=3, median_monthly=65000, negotiable=1))
    c = TestClient(create_app(db_path=str(tmp_path / "db.sqlite")))
    r = c.get("/api/salary-insights", params={"kw": "後端"})
    assert r.status_code == 200
    body = r.json()
    assert body["median_monthly"] == 65000 and body["sample"] == 3


def test_salary_endpoint_empty_kw_400(tmp_path):
    c = TestClient(create_app(db_path=str(tmp_path / "db.sqlite")))
    r = c.get("/api/salary-insights", params={"kw": "  "})
    assert r.status_code == 400
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_salary.py -q`
Expected: FAIL（404）

- [ ] **Step 3: 加端點**

在 `src/career_sentinel/web/routers/jobs.py`：把 `salary_insights` 加進檔頭 `from ... import ...`（與 `config, jobfetch, ...` 同一行或新增一行 `from ... import salary_insights`）。加端點（放既有某 GET endpoint 之後）：

```python
@router.get("/api/salary-insights")
def salary_insights_ep(kw: str = "", pages: int = 3) -> dict:
    if not kw.strip():
        raise HTTPException(status_code=400, detail="請輸入關鍵字")
    try:
        result = salary_insights.salary_insights_for_keyword(kw.strip(), pages=pages)
    except Exception:
        raise HTTPException(status_code=502, detail="查詢薪資行情失敗，請重試")
    return result.model_dump()
```

- [ ] **Step 4: 前端 api 型別與呼叫**

在 `web/frontend/src/api.ts` 加：

```typescript
export interface SalaryInsight {
  keyword: string;
  sample: number;
  negotiable: number;
  hourly_excluded: number;
  median_monthly: number | null;
  p25_monthly: number | null;
  p75_monthly: number | null;
  min_monthly: number | null;
  max_monthly: number | null;
}

export async function getSalaryInsights(kw: string): Promise<Response> {
  return fetch(`/api/salary-insights?kw=${encodeURIComponent(kw)}`);
}
```

- [ ] **Step 5: 跑測試確認通過（含全套）+ 前端建置**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠 + 2 新端點測試通過。
Run: `cd web/frontend && npm run build`
Expected: build 成功。

- [ ] **Step 6: Commit**

```bash
git add src/career_sentinel/web/routers/jobs.py web/frontend/src/api.ts tests/test_web_salary.py
git commit -m "feat(sentinel): /api/salary-insights 端點 + 前端 api 型別"
```

---

### Task 4: 聊天唯讀工具 `salary_insights`

**Files:**
- Modify: `src/career_sentinel/chat/tools.py`
- Modify: `src/career_sentinel/chat/prompt.py`
- Test: `tests/test_chat_tools.py`

**Interfaces:**
- Consumes: `salary_insights.salary_insights_for_keyword`。
- Produces: `salary_insights` 工具（`TOOLS` + `_execute_tool` 分派 + `_execute_salary_insights`）。

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_chat_tools.py` 末尾加：

```python
def test_execute_tool_salary_insights(monkeypatch):
    import json
    from career_sentinel import salary_insights
    from career_sentinel.models import SalaryInsight
    monkeypatch.setattr(salary_insights, "salary_insights_for_keyword",
                        lambda kw, **kw2: SalaryInsight(keyword=kw, sample=5, median_monthly=60000))
    event, text, is_error = chat._execute_tool("salary_insights", {"keyword": "後端"}, None)
    assert event is None and is_error is False
    assert json.loads(text)["median_monthly"] == 60000


def test_system_prompt_mentions_salary_insights():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "salary_insights" in p
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py::test_execute_tool_salary_insights tests/test_chat_tools.py::test_system_prompt_mentions_salary_insights -q`
Expected: FAIL（未知工具 / 提示未提及）

- [ ] **Step 3: 加工具定義、分派、執行體**

在 `src/career_sentinel/chat/tools.py`：`TOOLS` list 加一項（`fetch_url` 之後）：

```python
    {
        "name": "salary_insights",
        "description": "查某職稱/關鍵字在 104 的薪資行情（月薪中位數與區間）。使用者問行情、談薪資或討論 offer 時可用。",
        "input_schema": {
            "type": "object",
            "properties": {"keyword": {"type": "string", "description": "職稱或關鍵字，如 後端工程師"}},
            "required": ["keyword"],
        },
    },
```

在 `_execute_tool` 的 `if name == "fetch_url":` 之後、`return None, f"未知工具：{name}", True` 之前加：

```python
    if name == "salary_insights":
        return _execute_salary_insights(str((tool_input or {}).get("keyword", "")))
```

在 `_pipeline_tool_json` 之後（或 `_execute_tool` 之前）加執行體：

```python
def _execute_salary_insights(keyword: str):
    """salary_insights 工具執行體。回 (None, JSON文字, is_error)。唯讀、需真網路。"""
    from .. import salary_insights

    kw = (keyword or "").strip()
    if not kw:
        return None, "缺少關鍵字", True
    try:
        r = salary_insights.salary_insights_for_keyword(kw, pages=3)
    except Exception:
        return None, "查詢薪資行情失敗，請稍後再試", True
    return None, r.model_dump_json(), False
```

- [ ] **Step 4: 系統提示工具段補一句**

在 `src/career_sentinel/chat/prompt.py` 的工具描述字串（`"工具：search_jobs ..."` 那段），在 `fetch_url ...` 之後、句尾「工具呼叫請節制」之前插入：

```
        "salary_insights 查某職稱/關鍵字的 104 薪資行情（談薪資或討論 offer 時可用）；"
```

- [ ] **Step 5: 跑測試確認通過（含全套）**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠 + 2 新測試通過。

- [ ] **Step 6: Commit**

```bash
git add src/career_sentinel/chat/tools.py src/career_sentinel/chat/prompt.py tests/test_chat_tools.py
git commit -m "feat(sentinel): 聊天唯讀工具 salary_insights"
```

---

### Task 5: 前端 `SalaryInsightPanel` + 找職缺頁掛載

**Files:**
- Create: `web/frontend/src/SalaryInsightPanel.tsx`
- Modify: `web/frontend/src/FindJobsPage.tsx`

**Interfaces:**
- Consumes: `getSalaryInsights`、`SalaryInsight`、`getPreferences`/`putPreferences`（Task 3 / 既有）。

- [ ] **Step 1: 建立 `SalaryInsightPanel.tsx`**

```tsx
import { Box, Button, Group, Paper, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getPreferences, getSalaryInsights, putPreferences, type SalaryInsight } from "./api";

export default function SalaryInsightPanel() {
  const qc = useQueryClient();
  const [kw, setKw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<SalaryInsight | null>(null);
  const [setting, setSetting] = useState(false);

  async function run() {
    if (!kw.trim()) return;
    setErr(null); setBusy(true); setData(null);
    try {
      const r = await getSalaryInsights(kw.trim());
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "查詢失敗"); return; }
      setData(b as SalaryInsight);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  async function setAsExpected() {
    if (!data?.median_monthly) return;
    setSetting(true);
    try {
      const prefs = await getPreferences();
      await putPreferences({ ...prefs, expected_salary: data.median_monthly });
      qc.invalidateQueries({ queryKey: ["preferences"] });
    } finally { setSetting(false); }
  }

  return (
    <Paper bg="dark.6" radius="md" p="md">
      <Text fw={600} size="sm" mb="sm">薪資行情（104 搜尋聚合）</Text>
      <Group wrap="nowrap" mb="sm">
        <TextInput style={{ flex: 1 }} placeholder="職稱關鍵字，如 後端工程師" value={kw}
          onChange={(e) => setKw(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }} />
        <Button onClick={run} loading={busy} disabled={!kw.trim()}>查行情</Button>
      </Group>
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {data && data.sample === 0 && (
        <Text size="sm" c="dimmed">這個關鍵字大多為面議（{data.negotiable} 筆），抓不到可統計的數字。</Text>
      )}
      {data && data.sample > 0 && (
        <Box>
          <Group align="baseline" gap={6}>
            <Text c="teal.4" fw={700} size="xl" ff="'Space Grotesk', sans-serif">
              {data.median_monthly?.toLocaleString()}
            </Text>
            <Text size="xs" c="dimmed">中位月薪</Text>
          </Group>
          <Text size="sm" c="dark.1">
            區間 {data.p25_monthly?.toLocaleString()}–{data.p75_monthly?.toLocaleString()}
            （全距 {data.min_monthly?.toLocaleString()}–{data.max_monthly?.toLocaleString()}）
          </Text>
          <Text size="xs" c="dimmed" mt={4}>
            樣本 {data.sample} 筆 · 面議 {data.negotiable} · 時薪排除 {data.hourly_excluded}
          </Text>
          <Button size="compact-sm" variant="light" mt="sm" loading={setting} onClick={setAsExpected}>
            設為期望月薪
          </Button>
        </Box>
      )}
    </Paper>
  );
}
```

- [ ] **Step 2: 找職缺頁掛載**

在 `web/frontend/src/FindJobsPage.tsx`：import 加 `import SalaryInsightPanel from "./SalaryInsightPanel";`。在 `<PageHeader ... />` 之後加一行：

```tsx
        <SalaryInsightPanel />
```

- [ ] **Step 3: 前端建置**

Run: `cd web/frontend && npm run build`
Expected: build 成功、無型別錯誤。

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/SalaryInsightPanel.tsx web/frontend/src/FindJobsPage.tsx
git commit -m "feat(sentinel): 找職缺頁薪資行情面板（含設為期望月薪）"
```

---

## Self-Review

**1. Spec coverage：** 結構化薪資 + 解析（Task 1）、聚合換算/中位分位/排除計數（Task 2）、`/api/salary-insights` + 前端型別（Task 3）、聊天唯讀工具（Task 4）、UI 面板 + 回填期望薪資（Task 5）全覆蓋。錯誤處理（kw 空 400 / 抓取 502 / 空樣本 None）與非目標（不接外部站、不改 negotiate）遵守。

**2. Placeholder scan：** 無 TBD/TODO；每步含完整程式碼；測試含實際斷言與預期。

**3. Type/名稱一致性：** `salary_low`/`salary_high`/`salary_period`、`SalaryInsight`（欄位 sample/negotiable/hourly_excluded/median_monthly/p25/p75/min/max）、`compute_salary_insights(keyword, jobs)`、`salary_insights_for_keyword(keyword, *, pages, session)`、`_salary_fields`、`getSalaryInsights`、`_execute_salary_insights` 在 model/模組/端點/工具/前端/測試間一致；`fetch_search(keyword, *, page, session)` 呼叫與既有簽名一致；中位測試值（97500）與 `_percentile` 內插一致（兩點：0.5×(2−1)=0.5→70000+(125000−70000)×0.5=97500）。
