# 面試準備助手 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 為 career-sentinel 加「面試準備助手」：依 JD + 履歷 + 比對缺口生可能考題/缺口防雷/亮點/準備清單（可選深度模式上網搜公司面試心得），存在職缺上，從職缺卡與聊天 agent 皆可觸發。

**Architecture:** 沿用既有 LLM 任務三段式（同 negotiate）：`interview_prep.py` 任務模組 + `InterviewPrep` model + `tracked_jobs.interview_prep_json` 持久化 + `POST /api/tracked/{code}/interview-prep` + 前端 `InterviewPrepView`/職缺卡按鈕/聊天 run-card。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI、sqlite；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- 快版（`deep=False`）走 `llm.parse_json`；深度版（`deep=True`）走 `research.web_search_complete` 搜公司面試心得、附 sources。
- 持久化於 `tracked_jobs.interview_prep_json`；**`merge_tracked_job` 與 `set_tracked_state` 的既有分支必須沿用帶回 `interview_prep_json`**（否則擷取/改狀態會清空，附回歸測試）。
- 需先有履歷（無 → 400「請先上傳履歷」）；抓 JD 失敗 → 502；LLM `RuntimeError` → 400；其他 → 500。
- 聊天 `interview_prep` 為 **run-card**（前端直接呼叫端點），**不進** `apply_update` 的 `ALLOWED`（同 tailor/negotiate）。
- 測試用專案 venv：`./.venv/Scripts/python.exe -m pytest -q`（cwd `sentinel/`）；前端 `cd web/frontend && npm run build`。
- 不改既有 tailor/negotiate/match 行為。

---

## 檔案結構

```
src/career_sentinel/
├─ models.py                    # + class InterviewPrep；TrackedJob + interview_prep_json
├─ store.py                     # schema/migrate/load/get/upsert + interview_prep_json；set_interview_prep；merge/set carry-forward
├─ interview_prep.py            # 新：build_interview_prep_prompt + prepare_interview
├─ chat/prompt.py               # _CONTRACT + interview_prep run-card 條目與規則
└─ web/routers/tracked.py       # + POST /api/tracked/{code}/interview-prep；tracked_get 回 interview_prep
web/frontend/src/
├─ api.ts                       # + InterviewPrep 型別、TrackedCard.interview_prep、interviewPrep()
├─ InterviewPrepView.tsx        # 新：InterviewPrepView 渲染 + InterviewPrepButton（職缺卡）
├─ JobCardDrawer.tsx            # 面試紀錄旁掛 InterviewPrepButton
└─ ChatPage.tsx                 # InterviewPrepCard（run-card）+ 渲染分支 + FIELD_LABEL
tests/
├─ test_tracked_jobs_store.py   # + set_interview_prep / carry-forward 回歸
├─ test_interview_prep.py       # 新：prompt + prepare_interview（快/深）
├─ test_web_interview_prep.py   # 新：端點
└─ test_chat_tools.py           # + contract mentions interview_prep
```

---

### Task 1: 資料層 — `InterviewPrep` model、`interview_prep_json` 欄、`set_interview_prep`、carry-forward

**Files:**
- Modify: `src/career_sentinel/models.py`
- Modify: `src/career_sentinel/store.py`
- Test: `tests/test_tracked_jobs_store.py`

**Interfaces:**
- Produces:
  - `models.InterviewPrep(likely_questions, gap_watchouts, talking_points, prep_checklist, sources: list[ResearchSource], deep: bool, prepared_at: str)` — 全部有預設。
  - `TrackedJob.interview_prep_json: str = ""`
  - `store.set_interview_prep(conn, code: str, prep: InterviewPrep) -> None`
  - `merge_tracked_job` / `set_tracked_state` 沿用 `interview_prep_json`；load/get/upsert 帶該欄。

- [ ] **Step 1: 加 `InterviewPrep` model**

在 `src/career_sentinel/models.py` 的 `class TailoredApplication` 之後加入：

```python
class InterviewPrep(BaseModel):
    likely_questions: list[str] = Field(default_factory=list)   # 可能考題
    gap_watchouts: list[str] = Field(default_factory=list)      # 缺口可能被追問 + 建議回法
    talking_points: list[str] = Field(default_factory=list)     # 你的亮點，主動帶出
    prep_checklist: list[str] = Field(default_factory=list)     # 面試前複習清單
    sources: list[ResearchSource] = Field(default_factory=list) # 深度模式才有
    deep: bool = False
    prepared_at: str = ""
```

在 `class TrackedJob` 的 `interviews_json: str = ""` 之後加一行：

```python
    interview_prep_json: str = ""
```

- [ ] **Step 2: 寫失敗測試（持久化 + carry-forward 回歸）**

在 `tests/test_tracked_jobs_store.py` 末尾加入：

```python
def test_set_interview_prep_persists(tmp_path):
    from career_sentinel import store
    from career_sentinel.models import InterviewPrep
    conn = store.connect(str(tmp_path / "db.sqlite"))
    store.merge_tracked_job(conn, "a", state="interested", company="甲")
    store.set_interview_prep(conn, "a", InterviewPrep(likely_questions=["為什麼想來"], deep=False))
    tj = store.get_tracked_job(conn, "a")
    assert tj.interview_prep_json
    import json
    assert json.loads(tj.interview_prep_json)["likely_questions"] == ["為什麼想來"]


def test_merge_preserves_interview_prep(tmp_path):
    from career_sentinel import store
    from career_sentinel.models import InterviewPrep
    conn = store.connect(str(tmp_path / "db.sqlite"))
    store.merge_tracked_job(conn, "a", state="interested")
    store.set_interview_prep(conn, "a", InterviewPrep(likely_questions=["Q"]))
    # 再次 merge（模擬擷取沿用）不得清空 interview_prep_json
    store.merge_tracked_job(conn, "a", state="matched", match_score=70)
    tj = store.get_tracked_job(conn, "a")
    assert tj.interview_prep_json and "Q" in tj.interview_prep_json


def test_set_tracked_state_preserves_interview_prep(tmp_path):
    from career_sentinel import store
    from career_sentinel.models import InterviewPrep
    conn = store.connect(str(tmp_path / "db.sqlite"))
    store.merge_tracked_job(conn, "a", state="interested")
    store.set_interview_prep(conn, "a", InterviewPrep(likely_questions=["Q"]))
    store.set_tracked_state(conn, "a", "rejected")  # 改狀態不得清空
    tj = store.get_tracked_job(conn, "a")
    assert tj.interview_prep_json and "Q" in tj.interview_prep_json
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_tracked_jobs_store.py -q`
Expected: FAIL（`set_interview_prep` 不存在 / 欄位未帶）

- [ ] **Step 4: store schema、migrate、load/get/upsert 加欄位**

在 `store.py`：
1. `_SCHEMA` 的 `tracked_jobs` CREATE，把最後一欄 `interviews_json TEXT NOT NULL DEFAULT ''` 改成兩欄（加逗號）：

```sql
    interviews_json TEXT NOT NULL DEFAULT '',
    interview_prep_json TEXT NOT NULL DEFAULT ''
```

2. `_migrate` 的欄位補齊迴圈加入新欄：

```python
    for col in ("match_json", "tailor_json", "offer_json", "interviews_json", "interview_prep_json"):
```

3. 匯入區把 `InterviewPrep` 加進 `from .models import (...)`。

4. `load_tracked_jobs`：SELECT 尾端加 `, interview_prep_json`，解包變數加 `ip`，`TrackedJob(...)` 加 `interview_prep_json=ip or ""`。完整替換該函式：

```python
def load_tracked_jobs(conn: sqlite3.Connection) -> list[TrackedJob]:
    rows = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json, interviews_json, interview_prep_json FROM tracked_jobs ORDER BY updated_at DESC"
    )
    return [
        TrackedJob(
            code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
            match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
            tailor_json=tj or "", offer_json=oj or "", interviews_json=iv or "", interview_prep_json=ip or "",
        )
        for c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj, iv, ip in rows
    ]
```

5. `get_tracked_job`：完整替換：

```python
def get_tracked_job(conn: sqlite3.Connection, code: str) -> TrackedJob | None:
    row = conn.execute(
        "SELECT code, company, title, url, salary, state, match_score, created_at, updated_at, "
        "match_json, tailor_json, offer_json, interviews_json, interview_prep_json FROM tracked_jobs WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        return None
    c, co, t, u, sa, st, ms, ca, ua, mj, tj, oj, iv, ip = row
    return TrackedJob(
        code=c, company=co or "", title=t or "", url=u or "", salary=sa or "", state=st,
        match_score=ms, created_at=ca or "", updated_at=ua or "", match_json=mj or "",
        tailor_json=tj or "", offer_json=oj or "", interviews_json=iv or "", interview_prep_json=ip or "",
    )
```

6. `upsert_tracked_job`：完整替換：

```python
def upsert_tracked_job(conn: sqlite3.Connection, job: TrackedJob) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO tracked_jobs "
        "(code, company, title, url, salary, state, match_score, created_at, updated_at, match_json, tailor_json, offer_json, interviews_json, interview_prep_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (job.code, job.company, job.title, job.url, job.salary, job.state,
         job.match_score, job.created_at, job.updated_at, job.match_json, job.tailor_json,
         job.offer_json, job.interviews_json, job.interview_prep_json),
    )
    conn.commit()
```

- [ ] **Step 5: `merge_tracked_job` / `set_tracked_state` carry-forward + `set_interview_prep`**

`merge_tracked_job`：existing 分支加 `new_ip = existing.interview_prep_json`；else 分支加 `new_ip = ""`；`upsert_tracked_job(conn, TrackedJob(...))` 的參數加 `interview_prep_json=new_ip`（與 `interviews_json=new_iv` 並列）。

`set_tracked_state`：existing 分支的 `upsert_tracked_job(conn, TrackedJob(...))` 加 `interview_prep_json=existing.interview_prep_json`（與 `interviews_json=existing.interviews_json` 並列）。else 分支（新建）不需加（預設空）。

在 `set_interviews` 之後加 `set_interview_prep`：

```python
def set_interview_prep(conn: sqlite3.Connection, code: str, prep: InterviewPrep) -> None:
    """整筆存某職缺的面試準備；保留其他欄位、updated_at=now；不存在則建列。"""
    now = datetime.now().isoformat(timespec="seconds")
    prep_json = prep.model_dump_json()
    existing = get_tracked_job(conn, code)
    if existing is not None:
        existing.interview_prep_json = prep_json
        existing.updated_at = now
        upsert_tracked_job(conn, existing)
    else:
        upsert_tracked_job(conn, TrackedJob(
            code=code, created_at=now, updated_at=now, interview_prep_json=prep_json))
```

- [ ] **Step 6: 跑測試確認通過（含全套回歸）**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 既有全綠 + 3 個新測試通過。

- [ ] **Step 7: Commit**

```bash
git add src/career_sentinel/models.py src/career_sentinel/store.py tests/test_tracked_jobs_store.py
git commit -m "feat(sentinel): InterviewPrep model + tracked interview_prep_json 持久化與 carry-forward"
```

---

### Task 2: LLM 任務 `interview_prep.py`

**Files:**
- Create: `src/career_sentinel/interview_prep.py`
- Test: `tests/test_interview_prep.py`

**Interfaces:**
- Consumes: `models.JobDetail`、`models.InterviewPrep`、`llm.parse_json`、`research.web_search_complete`、`llm._extract_json`。
- Produces:
  - `build_interview_prep_prompt(jd: JobDetail, resume_text: str, gaps: list[str], target_title: str, *, deep: bool) -> str`
  - `prepare_interview(jd, resume_text, gaps, target_title, *, deep=False, client=None, feature="面試準備") -> InterviewPrep`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_interview_prep.py`：

```python
import json

from career_sentinel import interview_prep, llm, research
from career_sentinel.models import InterviewPrep, JobDetail


_JD = JobDetail(title="後端工程師", company="甲公司", description="需 Python、FastAPI、SQL 三年經驗",
                work_exp="3 年以上", education="大學", specialties=["Python", "FastAPI"])


def test_prompt_contains_jd_resume_gaps_and_deep(monkeypatch):
    p = interview_prep.build_interview_prep_prompt(
        _JD, "我做過 Django 專案", ["缺 FastAPI 經驗"], "後端工程師", deep=False)
    assert "後端工程師" in p and "甲公司" in p and "Django" in p and "缺 FastAPI 經驗" in p
    assert "面試心得" not in p  # 快版不談搜尋
    p2 = interview_prep.build_interview_prep_prompt(_JD, "履歷", [], "後端工程師", deep=True)
    assert "面試心得" in p2 and "甲公司" in p2  # 深度版指示搜公司面試心得


def test_prepare_interview_fast(monkeypatch):
    def fake_parse(prompt, model_cls, *, system=None, client=None, feature=""):
        return model_cls.model_validate({
            "likely_questions": ["為什麼想來甲公司"],
            "gap_watchouts": ["會被追問 FastAPI"],
            "talking_points": ["Django 經驗可遷移"],
            "prep_checklist": ["複習 FastAPI 基礎"],
        })
    monkeypatch.setattr(llm, "parse_json", fake_parse)
    r = interview_prep.prepare_interview(_JD, "履歷", ["缺 FastAPI"], "後端工程師", deep=False)
    assert isinstance(r, InterviewPrep)
    assert r.deep is False and r.prepared_at
    assert r.likely_questions == ["為什麼想來甲公司"] and r.sources == []


def test_prepare_interview_deep_uses_web_search(monkeypatch):
    payload = {
        "likely_questions": ["系統設計"], "gap_watchouts": [], "talking_points": [],
        "prep_checklist": [], "sources": [{"title": "Dcard 面試心得", "url": "https://dcard.tw/x"}],
    }
    monkeypatch.setattr(research, "web_search_complete",
                        lambda prompt, *, feature, client=None: json.dumps(payload, ensure_ascii=False))
    r = interview_prep.prepare_interview(_JD, "履歷", [], "後端工程師", deep=True)
    assert r.deep is True and len(r.sources) == 1 and r.sources[0].url == "https://dcard.tw/x"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_interview_prep.py -q`
Expected: FAIL（`career_sentinel.interview_prep` 不存在）

- [ ] **Step 3: 實作 `interview_prep.py`**

建立 `src/career_sentinel/interview_prep.py`：

```python
"""面試準備助手：依 JD + 履歷 + 缺口生考題/防雷/亮點/清單；深度模式加網搜公司面試心得。"""
from __future__ import annotations

import json
from datetime import datetime

from . import llm, research
from .models import InterviewPrep, JobDetail

_RESUME_MAX = 6000


def build_interview_prep_prompt(jd: JobDetail, resume_text: str, gaps: list[str],
                                target_title: str, *, deep: bool) -> str:
    lines = [
        f"我下週要面試「{jd.company or '（公司未知）'}」的「{jd.title or target_title or '（職稱未知）'}」，"
        "請幫我做面試準備。",
        "",
        "職缺 JD：",
        f"- 職稱：{jd.title}",
        f"- 公司：{jd.company}",
        f"- 需求經驗：{jd.work_exp}；學歷：{jd.education}",
        f"- 專長技能：{'、'.join(jd.specialties) or '（未列）'}",
        f"- JD 內文：{(jd.description or '')[:2000]}",
        "",
        f"我的履歷（前 {_RESUME_MAX} 字）：\n{resume_text[:_RESUME_MAX] or '（未提供）'}",
    ]
    if gaps:
        lines += ["", "我對這個職缺的已知缺口（比對結果）：", *[f"- {g}" for g in gaps]]
    else:
        lines += ["", "（沒有現成的缺口分析，請你從 JD 與我的履歷自行推斷我可能被追問的弱點。）"]
    if deep:
        lines += [
            "",
            f"請用網路搜尋「{jd.company}」這間公司在台灣的面試心得與考古題"
            "（可參考 Dcard、PTT Tech_Job、Glassdoor、面試趣），把常見題型與面試流程納入考量；"
            "sources 只列實際參考到的網頁。",
        ]
    lines += [
        "",
        "只輸出單一 JSON 物件（不要 markdown 圍欄、不要其他文字），格式：",
        '{"likely_questions": ["可能被問的題目…"], '
        '"gap_watchouts": ["針對我缺口可能被追問的點 + 建議怎麼回…"], '
        '"talking_points": ["我該主動帶出的亮點…"], '
        '"prep_checklist": ["面試前要複習/準備的項目…"]'
        + (', "sources": [{"title": "來源標題", "url": "https://…"}]' if deep else "")
        + "}",
    ]
    return "\n".join(lines)


def prepare_interview(jd: JobDetail, resume_text: str, gaps: list[str], target_title: str,
                      *, deep: bool = False, client=None, feature: str = "面試準備") -> InterviewPrep:
    prompt = build_interview_prep_prompt(jd, resume_text, gaps, target_title, deep=deep)
    if deep:
        text = research.web_search_complete(prompt, feature=feature, client=client)
        r = InterviewPrep.model_validate(json.loads(llm._extract_json(text)))
    else:
        r = llm.parse_json(prompt, InterviewPrep, feature=feature, client=client)
    r.deep = deep
    r.prepared_at = datetime.now().isoformat(timespec="seconds")
    return r
```

- [ ] **Step 4: 跑測試確認通過**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_interview_prep.py -q`
Expected: 3 個測試通過。

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/interview_prep.py tests/test_interview_prep.py
git commit -m "feat(sentinel): interview_prep LLM 任務（快版 + 深度網搜）"
```

---

### Task 3: API 端點 + `tracked_get` 帶 interview_prep + 前端 api

**Files:**
- Modify: `src/career_sentinel/web/routers/tracked.py`
- Modify: `web/frontend/src/api.ts`
- Test: `tests/test_web_interview_prep.py`

**Interfaces:**
- Consumes: `interview_prep.prepare_interview`、`store.set_interview_prep`、`store.get_tracked_job`、`jobfetch.fetch_job_detail`、`models.MatchResult`。
- Produces: `POST /api/tracked/{code}/interview-prep`（body `{deep: bool}`）；`GET /api/tracked/{code}` 回應多 `interview_prep`；前端 `InterviewPrep` 型別、`TrackedCard.interview_prep`、`interviewPrep(code, deep)`。

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_web_interview_prep.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel import interview_prep as ip_mod, jobfetch, store
from career_sentinel.models import InterviewPrep, JobDetail
from career_sentinel.web.app import create_app


def _seed_resume(conn):
    st = store.load_resume(conn)
    st.resume_text = "我有三年後端經驗"
    store.save_resume(conn, st)


def test_interview_prep_endpoint_ok(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    _seed_resume(conn)
    store.merge_tracked_job(conn, "abc12", state="interested", company="甲", title="後端")
    monkeypatch.setattr(jobfetch, "fetch_job_detail", lambda code, **kw: JobDetail(title="後端", company="甲"))
    monkeypatch.setattr(ip_mod, "prepare_interview",
                        lambda jd, resume, gaps, title, **kw: InterviewPrep(likely_questions=["Q1"], deep=kw.get("deep", False)))
    c = TestClient(create_app(db_path=db))
    r = c.post("/api/tracked/abc12/interview-prep", json={"deep": False})
    assert r.status_code == 200
    assert r.json()["likely_questions"] == ["Q1"]
    # 已存檔：GET 帶出
    g = c.get("/api/tracked/abc12").json()
    assert g["interview_prep"]["likely_questions"] == ["Q1"]


def test_interview_prep_requires_resume(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    c = TestClient(create_app(db_path=db))
    r = c.post("/api/tracked/abc12/interview-prep", json={"deep": False})
    assert r.status_code == 400 and "履歷" in r.json()["detail"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_interview_prep.py -q`
Expected: FAIL（404 / 端點不存在）

- [ ] **Step 3: 加端點與 tracked_get 欄位**

在 `src/career_sentinel/web/routers/tracked.py`：
1. 匯入：把 `interview_prep, jobfetch` 加進 `from ... import store`（→ `from ... import interview_prep, jobfetch, store`）；`from ...models import InterviewNote, OfferDetail` 加 `MatchResult`（→ `..., MatchResult, OfferDetail`）。
2. `tracked_get`：在 found=True 的回傳 dict（含 `"interviews": ...` 那個）加一鍵：

```python
        "interview_prep": json.loads(tj.interview_prep_json) if tj.interview_prep_json else None,
```

在 found=False 的回傳 dict（`tj is None` 時）加 `"interview_prep": None`（與既有 `"interviews": []` 並列）。

3. 加請求 model 與端點（放在既有 `_InterviewsReq` 附近 / `set_interviews_ep` 之後）：

```python
class _InterviewPrepReq(BaseModel):
    deep: bool = False


@router.post("/api/tracked/{code}/interview-prep")
def interview_prep_ep(code: str, req: _InterviewPrepReq, db_path: str = Depends(get_db_path)) -> dict:
    if not code.strip():
        raise HTTPException(status_code=400, detail="缺少職缺代碼")
    conn = store.connect(db_path)
    resume = store.load_resume(conn)
    if not resume.resume_text.strip():
        raise HTTPException(status_code=400, detail="請先上傳履歷")
    try:
        jd = jobfetch.fetch_job_detail(code)
    except Exception:
        raise HTTPException(status_code=502, detail="抓取職缺失敗，請確認職缺代碼")
    tj = store.get_tracked_job(conn, code)
    gaps: list[str] = []
    if tj is not None and tj.match_json:
        try:
            gaps = MatchResult.model_validate_json(tj.match_json).gaps
        except Exception:
            gaps = []
    prefs = store.load_preferences(conn)
    try:
        prep = interview_prep.prepare_interview(jd, resume.resume_text, gaps, prefs.target_title, deep=req.deep)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="產生面試準備失敗，請重試")
    store.set_interview_prep(conn, code, prep)
    return prep.model_dump()
```

- [ ] **Step 4: 前端 api 型別與呼叫**

在 `web/frontend/src/api.ts`：`InterviewNote` 型別附近加 `InterviewPrep` 型別（`ResearchSource` 已存在、供 NegotiationAdvice 用）：

```typescript
export interface InterviewPrep {
  likely_questions: string[];
  gap_watchouts: string[];
  talking_points: string[];
  prep_checklist: string[];
  sources: ResearchSource[];
  deep: boolean;
  prepared_at: string;
}
```

`TrackedCard` 介面加一欄：

```typescript
  interview_prep: InterviewPrep | null;
```

加呼叫函式（`setInterviews` 附近）：

```typescript
export async function interviewPrep(code: string, deep: boolean): Promise<Response> {
  return fetch(`/api/tracked/${encodeURIComponent(code)}/interview-prep`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deep }),
  });
}
```

- [ ] **Step 5: 跑測試確認通過（含全套）+ 前端建置**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠 + 2 個新端點測試通過。
Run: `cd web/frontend && npm run build`
Expected: build 成功（型別正確）。

- [ ] **Step 6: Commit**

```bash
git add src/career_sentinel/web/routers/tracked.py web/frontend/src/api.ts tests/test_web_interview_prep.py
git commit -m "feat(sentinel): /api/tracked/{code}/interview-prep 端點 + 前端 api 型別"
```

---

### Task 4: 前端 UI（InterviewPrepView / 職缺卡按鈕 / 聊天 run-card）+ 聊天契約

**Files:**
- Create: `web/frontend/src/InterviewPrepView.tsx`
- Modify: `web/frontend/src/JobCardDrawer.tsx`
- Modify: `web/frontend/src/ChatPage.tsx`
- Modify: `src/career_sentinel/chat/prompt.py`（`_CONTRACT` 加 interview_prep 條目與規則）
- Test: `tests/test_chat_tools.py`（contract 提及）

**Interfaces:**
- Consumes: `api.interviewPrep`、`api.InterviewPrep`、`api.getTrackedJob`（JobCardDrawer 已用）。
- Produces: `InterviewPrepView`（渲染）、`InterviewPrepButton`（職缺卡）、`ChatPage` 內 `InterviewPrepCard`（run-card）。

- [ ] **Step 1: 聊天契約加 interview_prep + 提及測試**

在 `src/career_sentinel/chat/prompt.py` 的 `_CONTRACT`：
1. 在 `<suggestions>` 範例 JSON 裡 `interview_note` 那筆之後加一行（注意逗號）：

```
  {"field": "interview_prep", "op": "run", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師"}}
```

2. 在規則區「面試紀錄（interview_note/set）」段之後加一段：

```
- 面試準備（interview_prep/run）：使用者面試前想準備某職缺（想知道可能考題、怎麼準備）時，提議
  {"field": "interview_prep", "op": "run", "payload": {"code": "...", "company": "...", "title": "..."}}.
  需使用者已上傳履歷；payload.code 必來自 get_pipeline/search_jobs 的實際結果、不得杜撰。
  這是**提議**，會等使用者按下才實際生成（花 LLM 錢；深度模式還會網搜）——你不要自行寫面試題或聲稱已完成，只丟提議卡。
```

在 `tests/test_chat_tools.py` 加測試：

```python
def test_system_prompt_mentions_interview_prep():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "interview_prep" in p
```

Run: `./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py::test_system_prompt_mentions_interview_prep -q`
Expected: PASS。

- [ ] **Step 2: 建立 `InterviewPrepView.tsx`**

```tsx
import { ActionIcon, Anchor, Button, Group, List, Loader, Modal, Stack, Switch, Text } from "@mantine/core";
import { IconNotebook } from "@tabler/icons-react";
import { useState } from "react";
import { interviewPrep, type InterviewPrep } from "./api";

export function InterviewPrepView({ data }: { data: InterviewPrep }) {
  return (
    <Stack gap="sm">
      {data.likely_questions.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>可能考題</Text>
          <List size="sm" spacing={4}>{data.likely_questions.map((q, i) => <List.Item key={i}>{q}</List.Item>)}</List>
        </div>
      )}
      {data.gap_watchouts.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="amber.5" mb={2}>缺口防雷</Text>
          <List size="sm" spacing={4}>{data.gap_watchouts.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
        </div>
      )}
      {data.talking_points.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="teal.5" mb={2}>你的亮點（主動帶出）</Text>
          <List size="sm" spacing={4}>{data.talking_points.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
        </div>
      )}
      {data.prep_checklist.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>準備清單</Text>
          <List size="sm" spacing={4}>{data.prep_checklist.map((p, i) => <List.Item key={i}>{p}</List.Item>)}</List>
        </div>
      )}
      {data.sources.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>參考來源</Text>
          <Stack gap={2}>
            {data.sources.map((s, i) => {
              const safe = /^https?:\/\//i.test(s.url) ? s.url : undefined;
              return safe
                ? <Anchor key={i} href={safe} target="_blank" rel="noopener noreferrer" size="xs">{s.title || s.url}</Anchor>
                : <Text key={i} size="xs" c="dimmed">{s.title || s.url}</Text>;
            })}
          </Stack>
        </div>
      )}
    </Stack>
  );
}

export default function InterviewPrepButton({ code, company, title, initial }: {
  code: string; company?: string; title?: string; initial?: InterviewPrep | null;
}) {
  const label = [company, title].filter(Boolean).join(" · ");
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [deep, setDeep] = useState(false);
  const [data, setData] = useState<InterviewPrep | null>(initial ?? null);

  async function run() {
    setErr(null); setBusy(true);
    try {
      const r = await interviewPrep(code, deep);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "產生失敗"); return; }
      setData(b as InterviewPrep);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <Button size="compact-sm" variant="light" leftSection={<IconNotebook size={14} />}
        onClick={() => setOpened(true)}>面試準備</Button>
      <Modal opened={opened} onClose={() => setOpened(false)} size="lg"
        title={label ? `面試準備：${label}` : "面試準備"}>
        <Group justify="space-between" mb="sm">
          <Switch checked={deep} onChange={(e) => setDeep(e.currentTarget.checked)}
            label="深度模式（上網搜公司面試心得，較慢）" size="sm" />
          <Button size="compact-sm" loading={busy} onClick={run}>
            {data ? "重新產生" : "產生"}
          </Button>
        </Group>
        {busy && (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">{deep ? "搜尋面試心得並整理中（約 20–60 秒）…" : "整理面試準備中…"}</Text>
          </Group>
        )}
        {err && !busy && <Text c="danger.6" size="sm">{err}</Text>}
        {data && !busy && (
          <Stack gap="sm">
            <InterviewPrepView data={data} />
            <Text size="xs" c="dimmed">產於 {data.prepared_at}{data.deep ? "（深度）" : ""}</Text>
          </Stack>
        )}
        {!data && !busy && !err && (
          <Text size="sm" c="dimmed">按「產生」依這個職缺的 JD 與你的履歷做面試準備。</Text>
        )}
      </Modal>
    </>
  );
}
```

（未用到的 `ActionIcon` import 請移除——最終只 import 實際用到的元件：`Anchor, Button, Group, List, Loader, Modal, Stack, Switch, Text`。）

- [ ] **Step 3: JobCardDrawer 掛按鈕**

在 `web/frontend/src/JobCardDrawer.tsx`：
1. import 加 `import InterviewPrepButton from "./InterviewPrepView";` 與型別 `type InterviewPrep`（併入既有 `from "./api"` 的型別 import）。
2. 加狀態 `const [prep, setPrep] = useState<InterviewPrep | null>(null);`（與 `notes` 並列）。
3. 在讀取 tracked card 的 `.then((c) => {...})`（設 `setNotes(...)` 那段）加一行 `setPrep(c.interview_prep ?? null);`。
4. 在「面試紀錄」區塊標題列（`<Text fw={600} mb="sm">面試紀錄</Text>` 附近）改為在其右側放按鈕，例如把該標題包成一個 Group：

```tsx
            <Group justify="space-between" mb="sm">
              <Text fw={600}>面試紀錄</Text>
              {job.code && <InterviewPrepButton code={job.code} company={job.company} title={job.title} initial={prep} />}
            </Group>
```

（移除原本單獨的 `<Text fw={600} mb="sm">面試紀錄</Text>`，避免重複。）

- [ ] **Step 4: ChatPage 加 InterviewPrepCard + 渲染分支 + FIELD_LABEL**

在 `web/frontend/src/ChatPage.tsx`：
1. import 補 `InterviewPrepView`（`import { InterviewPrepView } from "./InterviewPrepView";`）與 `api` 的 `interviewPrep`、型別 `InterviewPrep`；Mantine 補 `Switch`（若未 import）。
2. `FIELD_LABEL` 加 `interview_prep: "面試準備",`。
3. 在 `NegotiateCard` 函式之後加 `InterviewPrepCard`：

```tsx
function InterviewPrepCard({ payload }: { payload: { code: string; company?: string; title?: string } }) {
  const [result, setResult] = useState<InterviewPrep | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [deep, setDeep] = useState(false);

  const run = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await interviewPrep(payload.code, deep);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "產生失敗"); return; }
      setResult(b as InterviewPrep);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };

  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>面試準備</b> {payload.company ?? ""}{payload.title ? ` · ${payload.title}` : ""}</Text>
        {!result && (
          <Group gap="xs" wrap="nowrap">
            <Switch checked={deep} onChange={(e) => setDeep(e.currentTarget.checked)} size="xs" label="深度" />
            <Button size="compact-xs" loading={busy} onClick={run}>產生</Button>
          </Group>
        )}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && <InterviewPrepView data={result} />}
    </Paper>
  );
}
```

4. 在渲染建議卡的三元運算（`s.field === "tailor" ? ... : s.field === "negotiate" ? ... : <SuggestionCard/>`）加一支：`s.field === "interview_prep"` → `<InterviewPrepCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />`。放在 negotiate 之後、`<SuggestionCard>` 之前。

- [ ] **Step 5: 前端建置 + 全套測試**

Run: `cd web/frontend && npm run build`
Expected: build 成功、無型別錯誤。
Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（含新的 contract 提及測試）。

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/InterviewPrepView.tsx web/frontend/src/JobCardDrawer.tsx web/frontend/src/ChatPage.tsx src/career_sentinel/chat/prompt.py tests/test_chat_tools.py
git commit -m "feat(sentinel): 面試準備 UI（職缺卡按鈕 + 聊天 run-card）+ 契約條目"
```

---

## Self-Review

**1. Spec coverage：** LLM 任務（Task 2，快/深）、`InterviewPrep` model + `interview_prep_json` 持久化 + carry-forward（Task 1）、`POST /interview-prep` + `tracked_get` 帶回 + 前端 api（Task 3）、職缺卡按鈕 + 聊天 run-card + 契約（Task 4）全覆蓋。錯誤處理（無履歷 400 / JD 502 / RuntimeError 400 / 其他 500）在 Task 3 端點。非目標（不重做面試心得記錄、深度外不接外部服務）遵守。

**2. Placeholder scan：** 無 TBD/TODO；每個程式步驟含完整程式碼；測試含實際斷言與預期。

**3. Type/名稱一致性：** `InterviewPrep` 欄位（likely_questions/gap_watchouts/talking_points/prep_checklist/sources/deep/prepared_at）在 model、任務、端點、前端型別、測試間一致；`prepare_interview(jd, resume_text, gaps, target_title, *, deep, client, feature)` 簽名在任務定義與端點呼叫一致；`set_interview_prep`、`interview_prep_json`、`interviewPrep(code, deep)`、`TrackedCard.interview_prep`、run-card field 名 `interview_prep` 全一致；carry-forward 變數 `new_ip` 與 upsert 欄位一致。
