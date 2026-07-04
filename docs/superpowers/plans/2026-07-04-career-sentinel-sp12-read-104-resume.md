# career-sentinel SP12 讀 104 履歷 + 健檢 + 開編輯頁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讀取真實 104 結構化履歷（登入態）→ 針對它做健檢（送 LLM 前剝除 PII）→ 開編輯頁使用者親手改。

**Architecture:** `scraper/resume104.py`（`parse_resume104` 純函式＋`fetch_resume104`/`resume104_session` 登入態讀取，同 recommend 模式）→ `GET /api/resume104`（on-demand、browser 序列化）＋`POST /api/resume104/diagnose`（`flatten_for_diagnosis` 剝 PII→重用 SP3 `diagnosis.diagnose`）→ 新分頁「104 履歷」＋開編輯頁（重用 SP11b `apply.open_job_page`）。agent 不寫入 104。

**Tech Stack:** Python 3.12、Pydantic v2、rebrowser-playwright（登入態讀）、既有 `diagnosis`/`apply`/`runner`、React 18 + Mantine 7。

**Spec:** `docs/superpowers/specs/2026-07-04-career-sentinel-sp12-read-104-resume-design.md`（spike 已完成、發現於 `spike/FINDINGS.md`）

## Global Constraints

- **agent 不寫入 104**：改履歷由使用者在編輯頁親手做（重用 SP11b `/api/apply/open`）。
- 讀取 on-demand、`try_begin_browser` 序列化（同 `/api/recommend`：忙碌 409、未登入 session None→409、失敗 502）。
- **PII 邊界**：讀取結果留本地顯示、不外送；健檢送 LLM 前用 `flatten_for_diagnosis` **排除 `is_pii=True`（info）區塊**。
- 端點：`GET /api/resume104`；`POST /api/resume104/diagnose` body `{target_title, resume104}`（前端回傳讀到的 Resume104）→ 重用 `diagnosis.diagnose(flat, target_title, None)`；無 key→400、生成失敗→500。
- 解析純函式防禦（`.get()`＋`isinstance`、壞筆略過不炸）；欄位型別依 spike 實測（見各 Task）。
- 測試不打真 LLM／真 104（假 payload fixture＋monkeypatch session）、**fixture 不含真實 PII**；輸出 pristine（僅既有 Starlette warning）。
- 前端：新分頁 value="resume104"；讀取/健檢/開編輯頁按鈕 loading＋try/finally；409/502 頁內 danger；Tabler icon 無 emoji；`npm run build` 零 TS 錯誤。不持久化。
- 不做（YAGNI）：本地 vs 104 diff、自動寫回、多份履歷管理、逐區塊編輯、快取。
- 分支 `dev`；commit `feat(sentinel): ...（SP12）`＋trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## File Structure

- Modify: `sentinel/src/career_sentinel/models.py`（Resume104Block/Resume104）
- Create: `sentinel/src/career_sentinel/scraper/resume104.py`
- Modify: `sentinel/src/career_sentinel/web/app.py`（2 端點）
- Modify: `sentinel/web/frontend/src/api.ts`、Create: `Resume104Page.tsx`、Modify: `App.tsx`/`Sidebar.tsx`
- Test: `sentinel/tests/test_resume104.py`（新）、`sentinel/tests/test_web_app.py`（追加）

後端指令在 `sentinel/` 下執行。

---

### Task 1: 模型 + `parse_resume104` + `flatten_for_diagnosis`

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（檔尾追加）
- Create: `sentinel/src/career_sentinel/scraper/resume104.py`（本 Task 只寫純函式部分）
- Test: `sentinel/tests/test_resume104.py`（新檔）

**Interfaces:**
- Produces: `Resume104Block(id, label, text, is_pii=False, completed=False)`、`Resume104(vno="", progress=0, blocks=[])`；`resume104.parse_resume104(payload: dict) -> Resume104`；`resume104.flatten_for_diagnosis(r: Resume104) -> str`。

**欄位型別（spike 實測，parser 依此）：**
- `data.resume.vno`(str)、`data.progress`(int)、`data.sidebar`=list[{id, completed}]。
- info(PII) 從 `data.ACData.info`：name/email/cellphone/street(str)、city=list[{des,no}]、birthYear(int)。
- experience `data.experience.formData.experiences[]`：companyName/jobName/description(str)、
  jobCat/industry=list[{no,des}]、duration=dict{startYear,startMonth,endYear,endMonth}、
  skill=list[{name?}]（可空）。
- education `data.education.formData.educations[]`：name(str)、departments=list[{name,type}]、
  highest/status=dict{text,value}、duration=dict{...}。
- skill `data.skill.formData.skills[]`：name/desc(str)、tag=list[{text,value}]。
- language `data.language.formData.languages.foreign`=list[{type,listening,speaking,...}]（type=dict{text,value}）。
- project `data.project.formData.projects[]`：name/introduction/url(str)、duration=dict{...}。
- bio `data.bio.formData.bio`：chi/eng(str)。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_resume104.py` 新檔——fixture 用假資料仿實測結構）

```python
from career_sentinel.models import Resume104
from career_sentinel.scraper import resume104


def _dur(y1, m1, y2, m2):
    return {"startYear": y1, "startMonth": m1, "endYear": y2, "endMonth": m2}


_PAYLOAD = {
    "data": {
        "resume": {"vno": "abc123"},
        "progress": 80,
        "sidebar": [{"id": "info", "completed": True}, {"id": "experience", "completed": True}],
        "ACData": {"info": {
            "name": "王小明", "email": "test@example.com", "cellphone": "0900000000",
            "city": [{"des": "台北市", "no": "1"}], "street": "測試路 1 號", "birthYear": 1998,
        }},
        "experience": {"formData": {"experiences": [{
            "companyName": "甲公司", "jobName": "後端工程師",
            "jobCat": [{"no": "1", "des": "軟體工程師"}],
            "duration": _dur(2020, 1, 2023, 6),
            "description": "負責 API 開發", "industry": [{"no": "2", "des": "軟體業"}],
        }]}},
        "education": {"formData": {"educations": [{
            "name": "測試大學", "departments": [{"name": "資工系", "type": "1"}],
            "highest": {"text": "學士", "value": 1}, "duration": _dur(2016, 9, 2020, 6),
            "status": {"text": "畢業", "value": 1},
        }]}},
        "skill": {"formData": {"skills": [{"name": "Python", "desc": "五年經驗", "tag": [{"text": "後端", "value": "1"}]}]}},
        "language": {"formData": {"languages": {"foreign": [{"type": {"text": "英文", "value": "1"}}]}}},
        "project": {"formData": {"projects": [{
            "name": "求職 agent", "duration": _dur(2024, 1, 2024, 6),
            "introduction": "本地求職工具", "url": "https://x",
        }]}},
        "bio": {"formData": {"bio": {"chi": "我是一位後端工程師…", "eng": ""}}},
    }
}


def test_parse_resume104_blocks():
    r = resume104.parse_resume104(_PAYLOAD)
    assert r.vno == "abc123" and r.progress == 80
    ids = [b.id for b in r.blocks]
    assert "info" in ids and "experience" in ids and "bio" in ids
    info = next(b for b in r.blocks if b.id == "info")
    assert info.is_pii is True and "王小明" in info.text and info.completed is True
    exp = next(b for b in r.blocks if b.id == "experience")
    assert exp.is_pii is False and "甲公司" in exp.text and "後端工程師" in exp.text and "2020" in exp.text
    edu = next(b for b in r.blocks if b.id == "education")
    assert "測試大學" in edu.text and "學士" in edu.text
    bio = next(b for b in r.blocks if b.id == "bio")
    assert "後端工程師" in bio.text


def test_parse_resume104_malformed_skips():
    assert resume104.parse_resume104({}).blocks == []
    assert resume104.parse_resume104({"data": {"experience": {"formData": {"experiences": [None, "x"]}}}}).vno == ""


def test_flatten_for_diagnosis_strips_pii():
    r = resume104.parse_resume104(_PAYLOAD)
    flat = resume104.flatten_for_diagnosis(r)
    # PII 不出現
    assert "王小明" not in flat and "test@example.com" not in flat and "0900000000" not in flat and "測試路" not in flat
    # 內容出現
    assert "甲公司" in flat and "後端工程師" in flat and "測試大學" in flat and "Python" in flat
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_resume104.py -q`
Expected: FAIL（ModuleNotFoundError / ImportError）

- [ ] **Step 3: 實作 models**（`sentinel/src/career_sentinel/models.py` 檔尾追加）

```python
class Resume104Block(BaseModel):
    id: str
    label: str
    text: str = ""
    is_pii: bool = False
    completed: bool = False


class Resume104(BaseModel):
    vno: str = ""
    progress: int = 0
    blocks: list[Resume104Block] = Field(default_factory=list)
```

- [ ] **Step 4: 實作 parse/flatten**（`sentinel/src/career_sentinel/scraper/resume104.py` 新檔）

```python
from __future__ import annotations

from ..models import Resume104, Resume104Block

RESUME_LIST_URL = "https://pda.104.com.tw/profile/ajax/completeResumeList?top=isMaster"
RESUME_BLOCK_URL = "https://pda.104.com.tw/profile/ajax/resumeByBlock?vno={vno}"

_LABELS = {
    "info": "基本資料", "experience": "工作經歷", "education": "學歷",
    "skill": "技能", "language": "語言", "project": "專案", "bio": "自傳",
}
# 內容區塊（非 PII）——健檢用
_CONTENT = ["experience", "education", "skill", "language", "project", "bio"]


def _s(v) -> str:
    return str(v).strip() if v is not None else ""


def _dur(d) -> str:
    if not isinstance(d, dict):
        return ""
    sy, sm = d.get("startYear"), d.get("startMonth")
    ey, em = d.get("endYear"), d.get("endMonth")
    start = f"{sy}/{sm}" if sy else ""
    end = f"{ey}/{em}" if ey else "至今"
    return f"{start} ~ {end}".strip(" ~") if start or ey else ""


def _des_join(lst) -> str:
    if not isinstance(lst, list):
        return ""
    return "、".join(_s(x.get("des")) for x in lst if isinstance(x, dict) and x.get("des"))


def _flatten_info(data: dict) -> str:
    info = (data.get("ACData") or {}).get("info") or {}
    if not isinstance(info, dict):
        return ""
    city = _des_join(info.get("city"))
    parts = [
        f"姓名：{_s(info.get('name'))}",
        f"Email：{_s(info.get('email'))}",
        f"手機：{_s(info.get('cellphone'))}",
        f"居住地：{city} {_s(info.get('street'))}".strip(),
    ]
    return "\n".join(p for p in parts if p.split("：", 1)[-1].strip())


def _flatten_experience(fd: dict) -> str:
    out = []
    for e in fd.get("experiences") or []:
        if not isinstance(e, dict):
            continue
        head = f"{_s(e.get('companyName'))}｜{_s(e.get('jobName'))}（{_dur(e.get('duration'))}）"
        lines = [head]
        cat = _des_join(e.get("jobCat"))
        if cat:
            lines.append(f"職類：{cat}")
        if _s(e.get("description")):
            lines.append(_s(e.get("description")))
        out.append("\n".join(lines))
    return "\n\n".join(out)


def _flatten_education(fd: dict) -> str:
    out = []
    for e in fd.get("educations") or []:
        if not isinstance(e, dict):
            continue
        dep = "、".join(_s(x.get("name")) for x in (e.get("departments") or []) if isinstance(x, dict))
        highest = _s((e.get("highest") or {}).get("text")) if isinstance(e.get("highest"), dict) else ""
        status = _s((e.get("status") or {}).get("text")) if isinstance(e.get("status"), dict) else ""
        out.append(f"{_s(e.get('name'))} {dep} {highest}（{_dur(e.get('duration'))}）{status}".strip())
    return "\n".join(out)


def _flatten_skill(fd: dict) -> str:
    out = []
    for s in fd.get("skills") or []:
        if not isinstance(s, dict):
            continue
        name = _s(s.get("name"))
        desc = _s(s.get("desc"))
        out.append(f"{name}：{desc}" if desc else name)
    return "\n".join(x for x in out if x)


def _flatten_language(fd: dict) -> str:
    langs = fd.get("languages")
    if not isinstance(langs, dict):
        return ""
    out = []
    for f in langs.get("foreign") or []:
        if isinstance(f, dict) and isinstance(f.get("type"), dict):
            out.append(_s(f["type"].get("text")))
    return "、".join(x for x in out if x)


def _flatten_project(fd: dict) -> str:
    out = []
    for p in fd.get("projects") or []:
        if not isinstance(p, dict):
            continue
        head = f"{_s(p.get('name'))}（{_dur(p.get('duration'))}）"
        intro = _s(p.get("introduction"))
        out.append(f"{head}\n{intro}" if intro else head)
    return "\n\n".join(out)


def _flatten_bio(fd: dict) -> str:
    bio = fd.get("bio")
    if not isinstance(bio, dict):
        return ""
    return _s(bio.get("chi")) or _s(bio.get("eng"))


_FLATTEN = {
    "experience": _flatten_experience, "education": _flatten_education,
    "skill": _flatten_skill, "language": _flatten_language,
    "project": _flatten_project, "bio": _flatten_bio,
}


def parse_resume104(payload: dict) -> Resume104:
    data = payload.get("data")
    if not isinstance(data, dict):
        return Resume104()
    vno = _s((data.get("resume") or {}).get("vno"))
    progress = data.get("progress") if isinstance(data.get("progress"), int) else 0
    sidebar = {
        _s(s.get("id")): bool(s.get("completed"))
        for s in (data.get("sidebar") or []) if isinstance(s, dict)
    }
    blocks: list[Resume104Block] = []
    info_text = _flatten_info(data)
    if info_text:
        blocks.append(Resume104Block(id="info", label=_LABELS["info"], text=info_text,
                                      is_pii=True, completed=sidebar.get("info", False)))
    for bid in _CONTENT:
        fd = (data.get(bid) or {}).get("formData") or {}
        text = _FLATTEN[bid](fd) if isinstance(fd, dict) else ""
        if text.strip():
            blocks.append(Resume104Block(id=bid, label=_LABELS[bid], text=text,
                                         is_pii=False, completed=sidebar.get(bid, False)))
    return Resume104(vno=vno, progress=progress, blocks=blocks)


def flatten_for_diagnosis(r: Resume104) -> str:
    """健檢用文字：只取非 PII 區塊，含區塊標題。"""
    return "\n\n".join(
        f"【{b.label}】\n{b.text}" for b in r.blocks if not b.is_pii and b.text.strip()
    )
```

- [ ] **Step 5: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（233＋新 3）

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/scraper/resume104.py sentinel/tests/test_resume104.py
git commit -m "feat(sentinel): Resume104 模型 + parse_resume104 + flatten_for_diagnosis（剝 PII）（SP12）"
```

---

### Task 2: `fetch_resume104` / `resume104_session` + 2 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/scraper/resume104.py`（檔尾追加 fetch/session）
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_app.py`（檔尾追加）

**Interfaces:**
- Consumes: Task 1 的 `parse_resume104`/`flatten_for_diagnosis`；既有 `browser.open_context/wait_until_ready/is_login_url`（同 recommend）、`runner.try_begin_browser/end_browser`、`diagnosis.diagnose`。
- Produces: `resume104.fetch_resume104(page) -> Resume104`、`resume104.resume104_session() -> Resume104 | None`；`GET /api/resume104`、`POST /api/resume104/diagnose`。

- [ ] **Step 1: 實作 fetch/session**（`sentinel/src/career_sentinel/scraper/resume104.py` 檔尾追加——需真瀏覽器、不單測，照 recommend 模式）

```python
_PROFILE_PAGE = "https://pda.104.com.tw/my/resume/list"


def fetch_resume104(page) -> Resume104:
    """需已登入且已取得 pda host clearance。需真瀏覽器、不單測。"""
    lst = page.request.get(RESUME_LIST_URL)
    if not lst.ok:
        raise RuntimeError(f"resume list HTTP {lst.status}")
    data = lst.json().get("data") or []
    vno = ""
    for r in data if isinstance(data, list) else []:
        if isinstance(r, dict) and r.get("vno"):
            vno = str(r.get("vno"))
            if r.get("isMaster") or r.get("master"):
                break
    if not vno:
        raise RuntimeError("找不到履歷 vno")
    blk = page.request.get(RESUME_BLOCK_URL.format(vno=vno))
    if not blk.ok:
        raise RuntimeError(f"resumeByBlock HTTP {blk.status}")
    return parse_resume104(blk.json())


def resume104_session() -> Resume104 | None:
    """開 headful context → 導覽 pda 履歷頁取 clearance + 確認登入 → 讀履歷。未登入回 None。"""
    from rebrowser_playwright.sync_api import sync_playwright

    from .. import browser

    with sync_playwright() as p:
        ctx = browser.open_context(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(_PROFILE_PAGE, wait_until="domcontentloaded")
            browser.wait_until_ready(page)
            if browser.is_login_url(page.url):
                return None
            return fetch_resume104(page)
        finally:
            ctx.close()
```

- [ ] **Step 2: 寫端點失敗測試**（`sentinel/tests/test_web_app.py` 檔尾追加）

```python
def test_resume104_get(tmp_path, monkeypatch):
    from career_sentinel.web import runner
    from career_sentinel.scraper import resume104
    from career_sentinel.models import Resume104, Resume104Block
    monkeypatch.setattr(runner, "try_begin_browser", lambda: True)
    monkeypatch.setattr(runner, "end_browser", lambda: None)
    monkeypatch.setattr(resume104, "resume104_session",
                        lambda: Resume104(vno="v1", progress=90, blocks=[
                            Resume104Block(id="info", label="基本資料", text="姓名：王", is_pii=True),
                            Resume104Block(id="experience", label="工作經歷", text="甲公司"),
                        ]))
    body = _client(tmp_path).get("/api/resume104").json()
    assert body["vno"] == "v1" and body["progress"] == 90
    assert [b["id"] for b in body["blocks"]] == ["info", "experience"]


def test_resume104_get_busy_and_not_logged_in(tmp_path, monkeypatch):
    from career_sentinel.web import runner
    from career_sentinel.scraper import resume104
    monkeypatch.setattr(runner, "try_begin_browser", lambda: False)
    assert _client(tmp_path).get("/api/resume104").status_code == 409
    monkeypatch.setattr(runner, "try_begin_browser", lambda: True)
    monkeypatch.setattr(runner, "end_browser", lambda: None)
    monkeypatch.setattr(resume104, "resume104_session", lambda: None)
    assert _client(tmp_path).get("/api/resume104").status_code == 409


def test_resume104_diagnose_strips_pii(tmp_path, monkeypatch):
    from career_sentinel import diagnosis
    from career_sentinel.models import ResumeDiagnosis
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    captured = {}
    def fake_diag(text, title, salary, **kw):
        captured["text"] = text
        return ResumeDiagnosis(strengths=["強"], gaps=["補"])
    monkeypatch.setattr(diagnosis, "diagnose", fake_diag)
    payload = {
        "target_title": "後端",
        "resume104": {"vno": "v1", "progress": 90, "blocks": [
            {"id": "info", "label": "基本資料", "text": "姓名：王小明\nEmail：a@b.c", "is_pii": True, "completed": True},
            {"id": "experience", "label": "工作經歷", "text": "甲公司 後端", "is_pii": False, "completed": True},
        ]},
    }
    body = _client(tmp_path).post("/api/resume104/diagnose", json=payload).json()
    assert body["strengths"] == ["強"]
    assert "王小明" not in captured["text"] and "a@b.c" not in captured["text"]  # PII 未送 LLM
    assert "甲公司" in captured["text"]
```

- [ ] **Step 3: 跑端點測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -q -k resume104`
Expected: FAIL（404）

- [ ] **Step 4: 實作端點**（`sentinel/src/career_sentinel/web/app.py`）

request model（`_ChatReq` 旁）：

```python
class _Resume104DiagnoseReq(BaseModel):
    target_title: str = ""
    resume104: dict
```

`/api/recommend` 端點之後追加：

```python
    @app.get("/api/resume104")
    def resume104_get() -> dict:
        from ..scraper import resume104
        if not runner.try_begin_browser():
            raise HTTPException(status_code=409, detail="瀏覽器忙碌中（可能正在抓取），請稍候再試")
        try:
            r = resume104.resume104_session()
        except Exception:
            raise HTTPException(status_code=502, detail="讀取 104 履歷失敗，請重試")
        finally:
            runner.end_browser()
        if r is None:
            raise HTTPException(status_code=409, detail="尚未登入，請先在終端機執行：career-sentinel login")
        return r.model_dump()

    @app.post("/api/resume104/diagnose")
    def resume104_diagnose(req: _Resume104DiagnoseReq) -> dict:
        from ..scraper import resume104
        from ..models import Resume104
        r = Resume104.model_validate(req.resume104)
        flat = resume104.flatten_for_diagnosis(r)
        if not flat.strip():
            raise HTTPException(status_code=400, detail="履歷內容為空，無法健檢")
        try:
            result = diagnosis.diagnose(flat, req.target_title or "（未指定）", None)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="健檢失敗，請重試")
        return result.model_dump()
```

- [ ] **Step 5: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/scraper/resume104.py sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_app.py
git commit -m "feat(sentinel): resume104 登入態讀取 + GET/diagnose 端點（PII 剝除）（SP12）"
```

---

### Task 3: 前端「104 履歷」分頁

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（檔尾追加）
- Create: `sentinel/web/frontend/src/Resume104Page.tsx`
- Modify: `sentinel/web/frontend/src/App.tsx`、`sentinel/web/frontend/src/Sidebar.tsx`

**Interfaces:**
- Consumes: Task 2 端點；SP11b `openApplyPage`（開編輯頁）；`getResume`（target_title 預設）、`PageContainer`/`PageHeader`。
- Produces: 第八分頁「104 履歷」。

- [ ] **Step 1: api.ts 追加**

```ts
export interface Resume104Block { id: string; label: string; text: string; is_pii: boolean; completed: boolean }
export interface Resume104 { vno: string; progress: number; blocks: Resume104Block[] }

export async function getResume104(): Promise<Response> {
  return fetch("/api/resume104");
}

export async function diagnoseResume104(target_title: string, resume104: Resume104): Promise<Response> {
  return fetch("/api/resume104/diagnose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_title, resume104 }),
  });
}
```
（`ResumeDiagnosis` 介面既有；`openApplyPage` 既有——複用開編輯頁。）

- [ ] **Step 2: Resume104Page.tsx 新檔**

```tsx
import { Badge, Button, Group, List, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconAlertTriangle, IconCheck, IconDownload, IconExternalLink } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  diagnoseResume104, getResume, getResume104, openApplyPage,
  type Resume104, type ResumeDiagnosis,
} from "./api";
import { PageContainer, PageHeader } from "./ui";

export default function Resume104Page() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [data, setData] = useState<Resume104 | null>(null);
  const [diag, setDiag] = useState<ResumeDiagnosis | null>(null);
  const [busy, setBusy] = useState(false);
  const [diagBusy, setDiagBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function read() {
    setErr(null); setDiag(null); setBusy(true);
    try {
      const r = await getResume104();
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "讀取失敗"); return; }
      setData(b);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  async function runDiag() {
    if (!data) return;
    setErr(null); setDiagBusy(true);
    try {
      const r = await diagnoseResume104(resume.data?.target_title ?? "", data);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "健檢失敗"); return; }
      setDiag(b);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setDiagBusy(false); }
  }

  async function openEdit() {
    if (!data?.vno) return;
    setErr(null); setApplyBusy(true);
    try {
      const r = await openApplyPage(`https://pda.104.com.tw/profile/edit?vno=${data.vno}`);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "開啟失敗"); }
    } catch { setErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  }

  return (
    <PageContainer>
      <PageHeader
        title="104 履歷"
        subtitle="讀取你 104 上的真實履歷、針對它健檢、開編輯頁親手修改"
        action={<Button onClick={read} loading={busy}>讀取我的 104 履歷</Button>}
      />
      {err && <Text c="danger.6" size="sm" mb="sm">{err}</Text>}
      {data && (
        <Stack gap="md">
          <Group>
            <Badge variant="light" color="teal">完成度 {data.progress}%</Badge>
            <Button size="compact-sm" variant="light" onClick={runDiag} loading={diagBusy}>健檢</Button>
            <Button size="compact-sm" leftSection={<IconExternalLink size={15} />}
              onClick={openEdit} loading={applyBusy}>開啟編輯頁</Button>
          </Group>

          {diag && (
            <Group align="flex-start" grow>
              <Paper bg="dark.6" radius="md" p="lg">
                <Group gap={8} mb="sm">
                  <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                  <Text fw={600}>優勢</Text>
                </Group>
                <List size="sm" spacing={6}>{diag.strengths.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
              </Paper>
              <Paper bg="dark.6" radius="md" p="lg">
                <Group gap={8} mb="sm">
                  <ThemeIcon variant="light" color="amber" size="sm"><IconAlertTriangle size={13} /></ThemeIcon>
                  <Text fw={600}>待補強</Text>
                </Group>
                <List size="sm" spacing={6}>{diag.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
              </Paper>
            </Group>
          )}

          {data.blocks.map((b) => (
            <Paper key={b.id} bg="dark.6" radius="md" p="lg">
              <Group gap={8} mb="xs">
                <Text fw={600}>{b.label}</Text>
                {b.is_pii && <Badge size="xs" variant="light" color="gray" leftSection={<IconDownload size={10} />}>個資（不送 LLM）</Badge>}
                {b.completed && <Badge size="xs" variant="light" color="teal">已完成</Badge>}
              </Group>
              <Text size="sm" c="dark.1" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{b.text}</Text>
            </Paper>
          ))}
        </Stack>
      )}
    </PageContainer>
  );
}
```

（`IconDownload` 僅為個資 badge 圖示佔位——實作可換 `IconLock`；若 build 缺該 icon 改用存在的 Tabler icon 並於報告註記。）

- [ ] **Step 3: Sidebar.tsx 加導覽項**

檔頭 tabler import 加 `IconId`；`PageKey` type 加 `| "resume104"`；`NAV` 陣列在 `resume` 之後插入：

```tsx
  { key: "resume104", label: "104 履歷", icon: IconId },
```

- [ ] **Step 4: App.tsx 加分頁**

檔頭加 `import Resume104Page from "./Resume104Page";`；在 `{page === "resume" && <ResumePage />}` 之後加：

```tsx
        {page === "resume104" && <Resume104Page />}
```

- [ ] **Step 5: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 零 TS 錯誤（未使用 import 清乾淨；若 IconDownload/IconId 不存在改用存在的 icon）

- [ ] **Step 6: Commit**

```bash
git add src/api.ts src/Resume104Page.tsx src/App.tsx src/Sidebar.tsx
git commit -m "feat(sentinel): 104 履歷分頁——讀取/健檢/開編輯頁（SP12）"
```

---

### Task 4: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`

- [ ] **Step 1: 真機驗證（需使用者操作）**

serve 重啟 → Ctrl+F5 → 側欄「104 履歷」分頁：
1. 「讀取我的 104 履歷」→ 登入態瀏覽器抓取 → 顯示各區塊（基本資料標「個資（不送 LLM）」、工作經歷/學歷/技能/自傳等）＋完成度
2. 「健檢」→ 針對真履歷產優勢/待補強（確認送 LLM 的內容不含姓名/email/電話——可看 digest 品質側面驗證）
3. 「開啟編輯頁」→ 登入態 Chrome 開 `profile/edit?vno=` → 在 104 親手改存
4. 忙碌情境：抓取進行中讀取 → 409；未登入 → 引導 login

- [ ] **Step 2: roadmap 收尾 + Commit**

SP12 表格列劃掉、✅ 區加摘要（含 spike 結論 resumeByBlock、PII 剝除、agent 不寫入）、review minors 記技術債區、更新日期。**backlog 至此清空**（僅剩 SP11b 已完成；SP12 為最後一項）。

```bash
git add docs/superpowers/career-sentinel-roadmap.md
git commit -m "docs(sentinel): SP12 讀 104 履歷+健檢完成（roadmap 收尾、backlog 清空）"
```
