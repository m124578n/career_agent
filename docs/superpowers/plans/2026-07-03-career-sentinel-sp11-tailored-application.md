# career-sentinel SP11 客製化履歷 + 求職信 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 貼 104 職缺網址 → 針對該職缺產「履歷客製化建議（強調重點/建議調整/該補關鍵字）＋求職信全文」，可讀、編輯、複製。

**Architecture:** `tailor.py`（照 `match.py` 模式：build_prompt + provider-aware `llm.parse_json`）→ `POST /api/tailor`（重用 SP4 jobfetch，同 `/api/match` 抓取路徑）→ 前端新分頁「客製化」（第七 Tab）。純本地 LLM、不快取、不碰投遞（SP11b）。

**Tech Stack:** Python 3.12、Pydantic v2、既有 `llm.parse_json`/`jobfetch`、FastAPI、React 18 + Mantine 7。

**Spec:** `docs/superpowers/specs/2026-07-03-career-sentinel-sp11-tailored-application-design.md`

## Global Constraints

- 重用既有：`jobfetch.extract_job_code(url)->str`（ValueError→400）、`jobfetch.fetch_job_detail(code)->JobDetail`（例外→502「抓取職缺失敗，請確認網址」）、`llm.parse_json(prompt, cls, *, system, client)`（無 key raise RuntimeError→400；今天日期由 `_with_today` 自動注入）。
- 履歷客製化只給**建議**（強調重點/建議調整/該補關鍵字），**不重寫履歷全文、不得捏造使用者沒有的經歷**；求職信 300–400 字繁體中文、對應該職缺、專業誠懇。
- 端點錯誤對映：無 job_url/壞網址→400、無履歷→400「請先上傳履歷」、無 key→400、抓取失敗→502、生成失敗→500「生成失敗，請重試」。**不快取**。
- 前端：新分頁 value="tailor"；未上傳履歷 disabled＋amber 引導；網路呼叫 try/finally；求職信複製用 `navigator.clipboard.writeText`；不持久化；Tabler icon 無 emoji；`npm run build` 零 TS 錯誤。
- 測試不打真 LLM／真 104（假 client＋monkeypatch）；輸出 pristine（僅既有 Starlette warning）。不碰投遞、不改 104 履歷、不快取、不匯出檔案。
- 分支 `dev`；commit `feat(sentinel): ...（SP11）`＋trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## File Structure

- Modify: `sentinel/src/career_sentinel/models.py`（TailoredApplication）
- Create: `sentinel/src/career_sentinel/tailor.py`
- Modify: `sentinel/src/career_sentinel/web/app.py`（POST /api/tailor）
- Modify: `sentinel/web/frontend/src/api.ts`、Create: `TailorPage.tsx`、Modify: `App.tsx`
- Test: `sentinel/tests/test_tailor.py`（新）、`sentinel/tests/test_web_app.py`（追加）

後端指令在 `sentinel/` 下執行。

---

### Task 1: 模型 + `tailor.py`

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（檔尾追加）
- Create: `sentinel/src/career_sentinel/tailor.py`
- Test: `sentinel/tests/test_tailor.py`（新檔）

**Interfaces:**
- Consumes: `llm.parse_json`、`models.JobDetail`。
- Produces: `TailoredApplication(job_title, company, resume_tips, resume_adjustments, missing_keywords, cover_letter)`；`tailor.build_prompt(resume_text, target_title, jd) -> str`；`tailor.tailor_application(resume_text, target_title, jd, *, client=None) -> TailoredApplication`。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_tailor.py` 新檔）

```python
import json

import pytest

from career_sentinel import tailor
from career_sentinel.models import JobDetail, TailoredApplication

_PAYLOAD = json.dumps({
    "resume_tips": ["強調 Python 五年經驗"],
    "resume_adjustments": ["把雲端經驗提前"],
    "missing_keywords": ["Kubernetes"],
    "cover_letter": "敬啟者：我對貴公司的後端職缺深感興趣……",
}, ensure_ascii=False)


class _FakeResp:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeHttp:
    def __init__(self, content):
        self._content = content
        self.captured = None

    def post(self, url, **kw):
        self.captured = {"url": url, **kw}
        return _FakeResp(self._content)


def _jd():
    return JobDetail(title="後端工程師", company="甲公司", description="需 Python 與雲端",
                     work_exp="3 年", education="大學", specialties=["Python", "AWS"])


def _openai_env(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    monkeypatch.setenv("LLM_MODEL", "m")


def test_tailor_parses(monkeypatch):
    _openai_env(monkeypatch)
    fake = _FakeHttp(_PAYLOAD)
    r = tailor.tailor_application("Python 五年", "後端工程師", _jd(), client=fake)
    assert r.resume_tips == ["強調 Python 五年經驗"]
    assert r.missing_keywords == ["Kubernetes"]
    assert r.cover_letter.startswith("敬啟者")
    # prompt 帶履歷全文與 JD
    sent = fake.captured["json"]["messages"][-1]["content"]
    assert "Python 五年" in sent and "後端工程師" in sent and "甲公司" in sent


def test_tailor_bad_json_raises(monkeypatch):
    _openai_env(monkeypatch)
    with pytest.raises(Exception):
        tailor.tailor_application("履歷", "後端", _jd(), client=_FakeHttp("沒有 JSON"))


def test_tailored_application_defaults():
    t = TailoredApplication()
    assert t.resume_tips == [] and t.cover_letter == "" and t.company == ""
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_tailor.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.tailor / ImportError TailoredApplication）

- [ ] **Step 3: 實作 models**（`sentinel/src/career_sentinel/models.py` 檔尾追加）

```python
class TailoredApplication(BaseModel):
    job_title: str = ""
    company: str = ""
    resume_tips: list[str] = Field(default_factory=list)
    resume_adjustments: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    cover_letter: str = ""
```

- [ ] **Step 4: 實作 tailor.py**（`sentinel/src/career_sentinel/tailor.py` 新檔）

```python
from __future__ import annotations

from . import llm
from .models import JobDetail, TailoredApplication

_SYSTEM = "你是一位專業的求職顧問，協助求職者針對特定職缺客製化履歷重點與求職信。"


def build_prompt(resume_text: str, target_title: str, jd: JobDetail) -> str:
    return (
        f"求職者目標職位：{target_title}\n"
        f"履歷全文：\n{resume_text}\n\n"
        f"目標職缺：{jd.title}（{jd.company}）\n"
        f"職缺需求：\n{jd.description}\n"
        f"工作經驗：{jd.work_exp}　學歷：{jd.education}\n"
        f"技能：{', '.join(jd.specialties)}\n\n"
        "請針對此職缺客製化，只回 JSON，格式：\n"
        '{"resume_tips": ["履歷中應強調的重點…"], '
        '"resume_adjustments": ["建議的調整…"], '
        '"missing_keywords": ["履歷缺少但職缺看重的關鍵字…"], '
        '"cover_letter": "求職信全文"}\n'
        "規則：resume_tips/adjustments 只給建議，**不要重寫整份履歷、不得捏造求職者沒有的經歷**；"
        "cover_letter 為 300–400 字繁體中文求職信，對應此職缺、語氣專業誠懇、"
        "只根據履歷已有的事實。"
    )


def tailor_application(
    resume_text: str, target_title: str, jd: JobDetail, *, client=None
) -> TailoredApplication:
    result = llm.parse_json(
        build_prompt(resume_text, target_title, jd),
        TailoredApplication,
        system=_SYSTEM,
        client=client,
    )
    result.job_title = jd.title
    result.company = jd.company
    return result
```

- [ ] **Step 5: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（219＋新 3）

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/tailor.py sentinel/tests/test_tailor.py
git commit -m "feat(sentinel): tailor.py——客製化履歷建議+求職信生成（SP11）"
```

---

### Task 2: `POST /api/tailor` 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_app.py`（檔尾追加）

**Interfaces:**
- Consumes: Task 1 的 `tailor.tailor_application`；既有 `jobfetch`、`store.load_resume`、`_MatchReq`（body `{job_url}`——重用）。
- Produces: `POST /api/tailor` → `TailoredApplication.model_dump()`。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_web_app.py` 檔尾追加）

```python
def test_tailor_endpoint(tmp_path, monkeypatch):
    from career_sentinel import jobfetch, tailor
    from career_sentinel.models import JobDetail, ResumeState, TailoredApplication
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    conn = store.connect(tmp_path / "db.sqlite")
    c = _client(tmp_path)

    # 無 job_url → 422/400（pydantic 缺欄位 422；空字串→400）
    assert c.post("/api/tailor", json={"job_url": ""}).status_code == 400

    store.save_resume(conn, ResumeState(resume_text="Python 五年", target_title="後端"))
    monkeypatch.setattr(jobfetch, "extract_job_code", lambda u: "abc")
    monkeypatch.setattr(jobfetch, "fetch_job_detail",
                        lambda code: JobDetail(title="後端工程師", company="甲公司"))
    monkeypatch.setattr(tailor, "tailor_application",
                        lambda rt, tt, jd, **kw: TailoredApplication(
                            job_title=jd.title, company=jd.company,
                            resume_tips=["強調 Python"], cover_letter="敬啟者…"))
    body = c.post("/api/tailor", json={"job_url": "https://www.104.com.tw/job/abc"}).json()
    assert body["job_title"] == "後端工程師" and body["company"] == "甲公司"
    assert body["resume_tips"] == ["強調 Python"] and body["cover_letter"] == "敬啟者…"


def test_tailor_endpoint_errors(tmp_path, monkeypatch):
    from career_sentinel import jobfetch
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    conn = store.connect(tmp_path / "db.sqlite")
    c = _client(tmp_path)
    monkeypatch.setattr(jobfetch, "extract_job_code", lambda u: "abc")
    # 無履歷 → 400
    assert c.post("/api/tailor", json={"job_url": "u"}).status_code == 400
    # 抓取失敗 → 502
    store.save_resume(conn, ResumeState(resume_text="履歷"))
    def boom(code):
        raise RuntimeError("boom")
    monkeypatch.setattr(jobfetch, "fetch_job_detail", boom)
    assert c.post("/api/tailor", json={"job_url": "u"}).status_code == 502
```

（`ResumeState` 已在 test_web_app.py 檔頭 import；若無，補 `from career_sentinel.models import ResumeState`。）

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -q -k tailor`
Expected: FAIL（404）

- [ ] **Step 3: 實作端點**（`sentinel/src/career_sentinel/web/app.py`）

import 行加入 `tailor`（字母序，在 `store,` 前 / `search`…實際位置：與既有 `match,` 併排）：

```python
from .. import calendar_link, chat as chatmod, company_link, config, diagnosis, diff, digest, jobfetch, llm, match, research, resume, store, tailor, watch
```

`match_job` 端點（`@app.post("/api/match")`…）**之後**追加：

```python
    @app.post("/api/tailor")
    def tailor_job(req: _MatchReq) -> dict:
        conn = _conn()
        if not req.job_url.strip():
            raise HTTPException(status_code=400, detail="請提供職缺網址")
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
            result = tailor.tailor_application(state.resume_text, state.target_title or "（未指定）", jd)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="生成失敗，請重試")
        return result.model_dump()
```

- [ ] **Step 4: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_app.py
git commit -m "feat(sentinel): POST /api/tailor——重用 SP4 jobfetch + 錯誤路徑（SP11）"
```

---

### Task 3: 前端「客製化」分頁

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（檔尾追加）
- Create: `sentinel/web/frontend/src/TailorPage.tsx`
- Modify: `sentinel/web/frontend/src/App.tsx`、`sentinel/web/frontend/src/Sidebar.tsx`

**Interfaces:**
- Consumes: Task 2 端點；`PageContainer`/`PageHeader`（ui.tsx）、`getResume`。
- Produces: 第七個分頁「客製化」。

- [ ] **Step 1: api.ts 追加**

```ts
export interface TailoredApplication {
  job_title: string;
  company: string;
  resume_tips: string[];
  resume_adjustments: string[];
  missing_keywords: string[];
  cover_letter: string;
}

export async function tailorApplication(job_url: string): Promise<Response> {
  return fetch("/api/tailor", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_url }),
  });
}
```

- [ ] **Step 2: TailorPage.tsx 新檔**

```tsx
import {
  ActionIcon, Button, Group, List, Paper, Stack, Text, TextInput, ThemeIcon,
} from "@mantine/core";
import { IconCheck, IconCopy, IconAlertTriangle } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getResume, tailorApplication, type TailoredApplication } from "./api";
import { PageContainer, PageHeader } from "./ui";

export default function TailorPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<TailoredApplication | null>(null);
  const [copied, setCopied] = useState(false);

  async function run() {
    if (!url.trim()) return;
    setErr(null);
    setData(null);
    setBusy(true);
    try {
      const r = await tailorApplication(url.trim());
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(body.detail ?? "生成失敗"); return; }
      setData(body);
    } catch {
      setErr("網路錯誤，請重試");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.cover_letter);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setErr("複製失敗");
    }
  }

  return (
    <PageContainer>
      <PageHeader title="客製化" subtitle="貼 104 職缺網址，針對該職缺產履歷客製化建議與求職信" />
      {!resume.data?.has_resume && (
        <Group gap={6} mb="sm">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-amber-5)" }} />
          <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷。</Text>
        </Group>
      )}
      <Group wrap="nowrap">
        <TextInput
          style={{ flex: 1 }}
          placeholder="https://www.104.com.tw/job/xxxxx"
          value={url}
          onChange={(e) => setUrl(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
        />
        <Button onClick={run} loading={busy} disabled={!resume.data?.has_resume || !url.trim()}>
          客製化
        </Button>
      </Group>
      {err && <Text c="danger.6" size="sm" mt="sm">{err}</Text>}
      {data && (
        <Stack gap="md" mt="lg">
          <Text fw={600}>{data.job_title}
            <Text span c="dimmed" size="sm"> · {data.company}</Text>
          </Text>
          {data.resume_tips.length > 0 && (
            <Paper bg="dark.6" radius="md" p="lg">
              <Group gap={8} mb="sm">
                <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                <Text fw={600}>要強調的重點</Text>
              </Group>
              <List size="sm" spacing={6}>{data.resume_tips.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </Paper>
          )}
          {data.resume_adjustments.length > 0 && (
            <Paper bg="dark.6" radius="md" p="lg">
              <Text fw={600} mb="sm">建議調整</Text>
              <List size="sm" spacing={6}>{data.resume_adjustments.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </Paper>
          )}
          {data.missing_keywords.length > 0 && (
            <Paper bg="dark.6" radius="md" p="lg">
              <Text fw={600} mb="sm">該補的關鍵字</Text>
              <Group gap={6}>
                {data.missing_keywords.map((k, i) => (
                  <Text key={i} size="sm" c="amber.5">{k}</Text>
                ))}
              </Group>
            </Paper>
          )}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>求職信</Text>
              <ActionIcon variant="subtle" color="gray" onClick={copy} title="複製求職信">
                {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              </ActionIcon>
            </Group>
            <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>{data.cover_letter}</Text>
          </Paper>
        </Stack>
      )}
    </PageContainer>
  );
}
```

- [ ] **Step 3: Sidebar.tsx 加導覽項**（`sentinel/web/frontend/src/Sidebar.tsx`）

檔頭 tabler import 加 `IconWand`；`PageKey` type 加 `| "tailor"`；`NAV` 陣列在 `search` 之後、`chat` 之前插入：

```tsx
  { key: "tailor", label: "客製化", icon: IconWand },
```

- [ ] **Step 4: App.tsx 加分頁**（`sentinel/web/frontend/src/App.tsx`）

檔頭加 `import TailorPage from "./TailorPage";`；在 `{page === "search" && <SearchPage />}` 之後加：

```tsx
        {page === "tailor" && <TailorPage />}
```

- [ ] **Step 5: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 零 TS 錯誤

- [ ] **Step 6: Commit**

```bash
git add src/api.ts src/TailorPage.tsx src/App.tsx src/Sidebar.tsx
git commit -m "feat(sentinel): 客製化分頁——建議+求職信+複製鍵（SP11）"
```

---

### Task 4: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`

- [ ] **Step 1: 真機驗證（需使用者操作）**

serve 重啟 → Ctrl+F5 → 側欄「客製化」分頁：
1. 貼一個面試中職缺的 104 網址 → 按「客製化」→ 出現要強調重點/建議調整/該補關鍵字/求職信全文
2. 求職信「複製」鍵 → 貼到別處確認內容
3. 未上傳履歷（或另一個乾淨 DB）→ 正確擋下並引導
4. 求職信品質：對應該職缺、無捏造經歷

- [ ] **Step 2: roadmap 收尾 + Commit**

SP11 表格列劃掉、✅ 區加摘要、review minors 記技術債區、更新日期（SP11b 保留待做）。

```bash
git add docs/superpowers/career-sentinel-roadmap.md
git commit -m "docs(sentinel): SP11 客製化履歷/求職信完成（roadmap 收尾）"
```
