# career-sentinel SP9 公司評價 web 研究 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 公司名旁一鍵查評價：LLM 自帶 web search 上網研究「{公司名} 評價/面試/薪資 台灣」→ 結構化報告（風險燈號/優缺點/薪資面試觀察/來源）→ Modal 顯示、SQLite 快取 7 天。

**Architecture:** Task 1 spike 驗證 provider web search 能力（gate，過不了就 BLOCKED 停止）→ `research.py` provider-aware 查詢＋解析 → `company_research` 公司名 KV 快取表 → `GET /api/research`（同步、TTL/force）→ 前端 `ResearchButton`（icon＋Modal）嵌入 Dashboard 各清單與 JobRow。

**Tech Stack:** Python 3.12、httpx（OpenAI 相容 `:online`）、anthropic SDK（Foundry `web_search` server tool）、Pydantic v2、FastAPI、React 18 + Mantine 7。

**Spec:** `docs/superpowers/specs/2026-07-03-career-sentinel-sp9-company-research-design.md`

## Global Constraints

- **Task 1 spike 是 gate**：兩個 provider 路徑都不支援 web search → 回報 BLOCKED、後續任務不執行。spike 結果若顯示呼叫格式與本計畫 Task 3 預設碼不同，以 spike 實測格式為準（controller 會在 Task 3 dispatch 中附上修正）。
- 查詢管道只用 LLM web search；**不做**本機爬搜尋引擎、**不做**評價站直抓。
- 快取：`RESEARCH_TTL_DAYS = 7`；7 天內回快取（`cached: true`）、`force=1` 強制重查；只有使用者主動點擊才查（不自動預查）。
- `risk_level` 白名單 `low|mid|high`，非法值落 `mid`（validator）。
- 端點：`company` 空→400、無 LLM key→400（訊息「請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY」）、查詢失敗→502「查詢失敗，請重試」。
- web search 呼叫 timeout 180 秒。
- PII：只送公司名（不新增出口類型）。
- 測試不打真 LLM（假 client）；spike（Task 1）與真機驗證（Task 6）才用真 key。測試輸出 pristine（僅允許既有第三方 StarletteDeprecationWarning）。
- 前端：網路呼叫 try/finally 解鎖；icon 按鈕帶 `title`；Tabler SVG icon 無 emoji；`npm run build` 零 TS 錯誤。
- 工作分支 `dev`；commit 風格 `feat(sentinel): ...（SP9）`＋trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## File Structure

- Create: `sentinel/spike/research_spike.py`（Task 1，驗證後保留為紀錄）
- Modify: `sentinel/src/career_sentinel/models.py`（ResearchSource/CompanyResearch）
- Modify: `sentinel/src/career_sentinel/store.py`（company_research KV 表＋load/save）
- Create: `sentinel/src/career_sentinel/research.py`（prompt/呼叫/解析/TTL）
- Modify: `sentinel/src/career_sentinel/web/app.py`（GET /api/research）
- Modify: `sentinel/web/frontend/src/api.ts`、Create: `ResearchButton.tsx`、Modify: `Dashboard.tsx`/`JobRow.tsx`
- Test: `sentinel/tests/test_research.py`（新）、`test_store.py`/`test_web_app.py`（追加）

後端指令在 `sentinel/` 下執行。

---

### Task 1: Spike——驗證 provider web search（GATE）

**Files:**
- Create: `sentinel/spike/research_spike.py`

**Interfaces:**
- Produces: spike 報告（哪個 provider 路徑可用、實際可用的呼叫格式、回應是否含真實網路資訊與來源、耗時）。

- [ ] **Step 1: 建立 spike 腳本**

```python
"""SP9 spike：驗證 LLM provider 的 web search 能力。

跑法：cd sentinel && uv run python spike/research_spike.py
判準：回覆內容包含「近期真實網路資訊」（非模型記憶）且最好附來源網址。
"""
import httpx

from career_sentinel.config import foundry_settings, llm_settings

PROMPT = (
    "請用網路搜尋查「台積電 面試 評價」，用繁體中文回覆一句你查到的重點，"
    "並附上一個實際來源網址。"
)


def try_openai_online() -> None:
    cfg = llm_settings()
    if not cfg.api_key:
        print("[openai] 無 LLM_API_KEY，略過")
        return
    variants = [
        ("model:online 後綴", {"model": cfg.model + ":online"}),
        ("plugins web", {"model": cfg.model, "plugins": [{"id": "web"}]}),
    ]
    for name, extra in variants:
        try:
            r = httpx.post(
                f"{cfg.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                json={**extra, "messages": [{"role": "user", "content": PROMPT}]},
                timeout=120,
            )
            print(f"[openai/{name}] status={r.status_code}")
            if r.status_code == 200:
                print("  content:", r.json()["choices"][0]["message"]["content"][:300])
        except Exception as exc:
            print(f"[openai/{name}] error: {exc}")


def try_foundry_web_search() -> None:
    fs = foundry_settings()
    if not fs.api_key:
        print("[foundry] 無 FOUNDRY_API_KEY，略過")
        return
    from anthropic import AnthropicFoundry

    client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    try:
        resp = client.messages.create(
            model=fs.model,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 2}],
            messages=[{"role": "user", "content": PROMPT}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        print("[foundry/web_search_20250305] ok:", text[:300])
    except Exception as exc:
        print(f"[foundry/web_search_20250305] error: {exc}")


if __name__ == "__main__":
    try_openai_online()
    try_foundry_web_search()
```

- [ ] **Step 2: 執行 spike**

Run: `cd sentinel && uv run python spike/research_spike.py`
Expected: 至少一個 provider 路徑回 200/ok 且內容是查到的網路資訊（含來源網址尤佳）。記錄：可用路徑、實際格式、耗時。

- [ ] **Step 3: 判定**

- 至少一路可用 → 在報告記錄可用格式與範例回應，繼續。
- 全部失敗 → 回報 **BLOCKED**（附各路徑的錯誤訊息），後續任務停止。

- [ ] **Step 4: Commit**

```bash
git add sentinel/spike/research_spike.py
git commit -m "spike(sentinel): 驗證 provider web search 能力（SP9 gate）"
```

---

### Task 2: 模型 + 快取表

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（檔尾追加）
- Modify: `sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_store.py`（檔尾追加）

**Interfaces:**
- Produces: `ResearchSource(title:str="", url:str="")`、`CompanyResearch(company, summary, pros, cons, salary_notes, interview_notes, risk_level="mid", sources, researched_at)`（risk_level validator 白名單）；`store.load_research(conn, company) -> CompanyResearch | None`、`store.save_research(conn, r) -> None`。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_store.py` 檔尾追加）

```python
def test_company_research_roundtrip(tmp_path):
    from career_sentinel.models import CompanyResearch, ResearchSource
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_research(conn, "台積電") is None
    r = CompanyResearch(
        company="台積電", summary="整體評價正面", pros=["福利好"], cons=["工時長"],
        salary_notes="高於同業", interview_notes="流程長", risk_level="low",
        sources=[ResearchSource(title="面試趣", url="https://interview.tw/x")],
        researched_at="2026-07-03T10:00:00",
    )
    store.save_research(conn, r)
    assert store.load_research(conn, "台積電") == r
    r2 = r.model_copy(update={"summary": "更新後"})
    store.save_research(conn, r2)  # 同公司覆寫
    assert store.load_research(conn, "台積電").summary == "更新後"


def test_company_research_risk_whitelist(tmp_path):
    from career_sentinel.models import CompanyResearch
    assert CompanyResearch(risk_level="weird").risk_level == "mid"
    assert CompanyResearch(risk_level="high").risk_level == "high"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_store.py -q -k research`
Expected: FAIL（AttributeError / ImportError）

- [ ] **Step 3: 實作 models**（`sentinel/src/career_sentinel/models.py` 檔尾追加）

```python
class ResearchSource(BaseModel):
    title: str = ""
    url: str = ""


class CompanyResearch(BaseModel):
    company: str = ""
    summary: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    salary_notes: str = ""
    interview_notes: str = ""
    risk_level: str = "mid"  # low | mid | high
    sources: list[ResearchSource] = Field(default_factory=list)
    researched_at: str = ""  # ISO

    @field_validator("risk_level", mode="before")
    @classmethod
    def _check_risk(cls, v):
        return v if v in ("low", "mid", "high") else "mid"
```

- [ ] **Step 4: 實作 store**（`sentinel/src/career_sentinel/store.py`）

`_SCHEMA` 的 `dismissed_interviews` 表之後追加：

```sql
CREATE TABLE IF NOT EXISTS company_research (
    company TEXT PRIMARY KEY, data TEXT NOT NULL
);
```

import 行的 `ChatState,` 後加入 `CompanyResearch,`（維持字母序）：

```python
from .models import (
    Application, ChatState, CompanyResearch, DismissedInterviews, Interview,
    JobPreferences, MemoryState, Message, ResumeState, Settings, Snapshot, Viewer,
)
```

檔尾追加：

```python
def load_research(conn: sqlite3.Connection, company: str) -> CompanyResearch | None:
    row = conn.execute(
        "SELECT data FROM company_research WHERE company = ?", (company,)
    ).fetchone()
    return CompanyResearch.model_validate_json(row[0]) if row else None


def save_research(conn: sqlite3.Connection, r: CompanyResearch) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO company_research (company, data) VALUES (?, ?)",
        (r.company, r.model_dump_json()),
    )
    conn.commit()
```

- [ ] **Step 5: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（既有 202＋新 2）

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_store.py
git commit -m "feat(sentinel): CompanyResearch 模型 + company_research 快取表（SP9）"
```

---

### Task 3: `research.py`（prompt / provider-aware 呼叫 / 解析 / TTL）

**Files:**
- Create: `sentinel/src/career_sentinel/research.py`
- Test: `sentinel/tests/test_research.py`（新檔）

**Interfaces:**
- Consumes: Task 2 的 `CompanyResearch`；`config.llm_provider()/llm_settings()/foundry_settings()`；`llm._extract_json`。
- Produces: `research_company(name: str, *, client=None) -> CompanyResearch`（無 key raise `RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")`）、`is_fresh(r: CompanyResearch, *, now: datetime | None = None) -> bool`、`RESEARCH_TTL_DAYS = 7`、`build_research_prompt(name) -> str`。
- **注意**：`_openai_research`/`_foundry_research` 的呼叫格式以 Task 1 spike 實測為準；若 controller 在 dispatch 中提供修正，以修正為準（下方為預設碼）。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_research.py` 新檔）

```python
import json
from datetime import datetime, timedelta

import pytest

from career_sentinel import research
from career_sentinel.models import CompanyResearch

_PAYLOAD = json.dumps({
    "summary": "整體評價正面",
    "pros": ["福利好"], "cons": ["工時長"],
    "salary_notes": "高於同業", "interview_notes": "流程長",
    "risk_level": "low",
    "sources": [{"title": "面試趣", "url": "https://interview.tw/x"}],
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


def _openai_env(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    monkeypatch.setenv("LLM_MODEL", "m")


def test_research_openai_parses(monkeypatch):
    _openai_env(monkeypatch)
    fake = _FakeHttp(_PAYLOAD)
    r = research.research_company("台積電", client=fake)
    assert r.company == "台積電"
    assert r.risk_level == "low" and r.pros == ["福利好"]
    assert r.researched_at  # 寫入當下時間
    assert fake.captured["json"]["model"] == "m:online"
    assert "台積電" in fake.captured["json"]["messages"][0]["content"]


def test_research_bad_json_raises(monkeypatch):
    _openai_env(monkeypatch)
    with pytest.raises(Exception):
        research.research_company("台積電", client=_FakeHttp("查不到喔（無 JSON）"))


def test_research_no_key_raises(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        research.research_company("台積電")


class _FakeAnthropicText:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeAnthropicResp:
    def __init__(self, text):
        self.content = [_FakeAnthropicText(text)]


class _FakeAnthropicMessages:
    def __init__(self, text):
        self._text = text
        self.captured = None

    def create(self, **kw):
        self.captured = kw
        return _FakeAnthropicResp(self._text)


class _FakeAnthropic:
    def __init__(self, text):
        self.messages = _FakeAnthropicMessages(text)


def test_research_foundry_uses_web_search_tool(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    fake = _FakeAnthropic(_PAYLOAD)
    r = research.research_company("台積電", client=fake)
    assert r.risk_level == "low"
    tools = fake.messages.captured["tools"]
    assert tools and tools[0]["name"] == "web_search"


def _stamp(dt):
    return dt.isoformat(timespec="seconds")


def test_is_fresh_ttl_boundary():
    now = datetime(2026, 7, 10, 12, 0, 0)
    fresh = CompanyResearch(researched_at=_stamp(now - timedelta(days=6, hours=23)))
    stale = CompanyResearch(researched_at=_stamp(now - timedelta(days=7, seconds=1)))
    assert research.is_fresh(fresh, now=now) is True
    assert research.is_fresh(stale, now=now) is False
    assert research.is_fresh(CompanyResearch(researched_at=""), now=now) is False
    assert research.is_fresh(CompanyResearch(researched_at="not-a-date"), now=now) is False
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_research.py -q`
Expected: FAIL（ModuleNotFoundError: career_sentinel.research）

- [ ] **Step 3: 實作**（`sentinel/src/career_sentinel/research.py` 新檔）

```python
"""SP9 公司評價 web 研究：LLM 自帶 web search 查評價、解析成 CompanyResearch。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx

from . import llm
from .config import foundry_settings, llm_provider, llm_settings
from .models import CompanyResearch

RESEARCH_TTL_DAYS = 7  # 快取有效天數
_TIMEOUT = 180  # web search 呼叫可能 20-60 秒，放寬


def build_research_prompt(name: str) -> str:
    return (
        f"請用網路搜尋研究台灣公司「{name}」的求職者評價。"
        f"建議搜尋關鍵字：「{name} 評價」「{name} 面試」「{name} 薪水 ptt dcard」。"
        "優先參考台灣站點（面試趣、比薪水、Dcard、PTT、Google 評論）。\n\n"
        "整理後只輸出單一 JSON 物件（不要 markdown 圍欄、不要任何其他文字），格式：\n"
        '{"summary": "總評一段（150字內）", "pros": ["優點…"], "cons": ["缺點…"], '
        '"salary_notes": "薪資觀察", "interview_notes": "面試觀察", '
        '"risk_level": "low|mid|high", '
        '"sources": [{"title": "來源標題", "url": "https://…"}]}\n'
        "規則：risk_level 依負評比例與嚴重度判斷（low=評價普遍正面、mid=毀譽參半或資料少、"
        "high=負評集中且嚴重）；查不到資料的欄位留空字串或空陣列，並在 summary 註明資料稀少；"
        "sources 只列你實際參考到的網頁。"
    )


def research_company(name: str, *, client=None) -> CompanyResearch:
    provider = llm_provider()
    prompt = build_research_prompt(name)
    if provider == "openai":
        text = _openai_research(prompt, client)
    elif provider == "foundry":
        text = _foundry_research(prompt, client)
    else:
        raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
    r = CompanyResearch.model_validate(json.loads(llm._extract_json(text)))
    r.company = name
    r.researched_at = datetime.now().isoformat(timespec="seconds")
    return r


def _openai_research(prompt, client):
    cfg = llm_settings()
    http = client or httpx.Client(timeout=_TIMEOUT)
    owns_client = client is None
    try:
        resp = http.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model + ":online",  # OpenRouter web search
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    finally:
        if owns_client:
            http.close()


def _foundry_research(prompt, client):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    resp = client.messages.create(
        model=fs.model,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")


def is_fresh(r: CompanyResearch, *, now: datetime | None = None) -> bool:
    """researched_at 在 TTL 內？空/壞格式視為過期。"""
    try:
        t = datetime.fromisoformat(r.researched_at)
    except ValueError:
        return False
    return ((now or datetime.now()) - t) <= timedelta(days=RESEARCH_TTL_DAYS)
```

- [ ] **Step 4: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/research.py sentinel/tests/test_research.py
git commit -m "feat(sentinel): research.py——web search 查評價 provider-aware + TTL（SP9）"
```

---

### Task 4: `GET /api/research` 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_app.py`（檔尾追加）

**Interfaces:**
- Consumes: Task 3 的 `research.research_company/is_fresh`、Task 2 的 `store.load_research/save_research`。
- Produces: `GET /api/research?company=<名>[&force=1]` → `CompanyResearch.model_dump() + {"cached": bool}`。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_web_app.py` 檔尾追加）

```python
def test_research_endpoint_cache_force_and_errors(tmp_path, monkeypatch):
    from datetime import datetime
    from career_sentinel import research
    from career_sentinel.models import CompanyResearch
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    calls = {"n": 0}

    def fake(name, **kw):
        calls["n"] += 1
        return CompanyResearch(
            company=name, summary=f"v{calls['n']}", risk_level="low",
            researched_at=datetime.now().isoformat(timespec="seconds"),
        )

    monkeypatch.setattr(research, "research_company", fake)
    c = _client(tmp_path)
    assert c.get("/api/research").status_code == 400  # 無 company
    r1 = c.get("/api/research", params={"company": "甲"}).json()
    assert r1["cached"] is False and r1["summary"] == "v1" and calls["n"] == 1
    r2 = c.get("/api/research", params={"company": "甲"}).json()
    assert r2["cached"] is True and calls["n"] == 1  # 快取命中不重查
    r3 = c.get("/api/research", params={"company": "甲", "force": 1}).json()
    assert r3["cached"] is False and r3["summary"] == "v2" and calls["n"] == 2


def test_research_endpoint_no_key_and_failure(tmp_path, monkeypatch):
    from career_sentinel import research
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    c = _client(tmp_path)
    assert c.get("/api/research", params={"company": "甲"}).status_code == 400
    monkeypatch.setenv("LLM_API_KEY", "k")

    def boom(name, **kw):
        raise ValueError("bad json")

    monkeypatch.setattr(research, "research_company", boom)
    assert c.get("/api/research", params={"company": "甲"}).status_code == 502
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -q -k research`
Expected: FAIL（404）

- [ ] **Step 3: 實作端點**（`web/app.py`）

import 行 `from .. import calendar_link, chat as chatmod, company_link, config, ...` 中，`config,` 前不動、在 `resume,` 後（字母序）加入 `research,`：

```python
from .. import calendar_link, chat as chatmod, company_link, config, diagnosis, diff, digest, jobfetch, llm, match, research, resume, store, watch
```

`create_app` 內、`/api/interviews/dismiss` 之前追加：

```python
    @app.get("/api/research")
    def research_get(company: str = "", force: int = 0) -> dict:
        name = company.strip()
        if not name:
            raise HTTPException(status_code=400, detail="請提供公司名稱")
        if not config.llm_provider():
            raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
        conn2 = _conn()
        cached = store.load_research(conn2, name)
        if cached and not force and research.is_fresh(cached):
            return {**cached.model_dump(), "cached": True}
        try:
            r = research.research_company(name)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=502, detail="查詢失敗，請重試")
        store.save_research(conn2, r)
        return {**r.model_dump(), "cached": False}
```

- [ ] **Step 4: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_app.py
git commit -m "feat(sentinel): GET /api/research——快取 TTL/force + 錯誤路徑（SP9）"
```

---

### Task 5: 前端 ResearchButton + 嵌入點

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（檔尾追加）
- Create: `sentinel/web/frontend/src/ResearchButton.tsx`
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`、`sentinel/web/frontend/src/JobRow.tsx`

**Interfaces:**
- Consumes: Task 4 端點。
- Produces: `ResearchButton({ company: string })` 元件。

- [ ] **Step 1: api.ts 追加**

```ts
export interface ResearchSource { title: string; url: string }
export interface CompanyResearch {
  company: string;
  summary: string;
  pros: string[];
  cons: string[];
  salary_notes: string;
  interview_notes: string;
  risk_level: string;
  sources: ResearchSource[];
  researched_at: string;
  cached: boolean;
}

export async function getResearch(company: string, force = false): Promise<Response> {
  return fetch(`/api/research?company=${encodeURIComponent(company)}${force ? "&force=1" : ""}`);
}
```

- [ ] **Step 2: ResearchButton.tsx 新檔**

```tsx
import {
  ActionIcon, Anchor, Badge, Button, Grid, Group, List, Loader, Modal, Stack, Text,
} from "@mantine/core";
import { IconZoomQuestion } from "@tabler/icons-react";
import { useState } from "react";
import { getResearch, type CompanyResearch } from "./api";

const RISK: Record<string, { color: string; label: string }> = {
  low: { color: "teal", label: "低風險" },
  mid: { color: "amber", label: "中性" },
  high: { color: "danger", label: "高風險" },
};

export default function ResearchButton({ company }: { company: string }) {
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<CompanyResearch | null>(null);

  async function load(force = false) {
    setErr(null);
    setBusy(true);
    try {
      const r = await getResearch(company, force);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(body.detail ?? "查詢失敗"); return; }
      setData(body);
    } catch {
      setErr("網路錯誤，請重試");
    } finally {
      setBusy(false);
    }
  }

  function open() {
    setOpened(true);
    if (!data && !busy) load();
  }

  const risk = RISK[data?.risk_level ?? "mid"] ?? RISK.mid;

  return (
    <>
      <ActionIcon variant="subtle" color="gray" size="xs" title="查公司評價"
        style={{ flexShrink: 0 }} onClick={open}>
        <IconZoomQuestion size={13} />
      </ActionIcon>
      <Modal opened={opened} onClose={() => setOpened(false)} size="lg"
        title={`公司評價：${company}`}>
        {busy && (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">上網研究中（約 20–60 秒）…</Text>
          </Group>
        )}
        {err && !busy && (
          <Stack align="flex-start">
            <Text c="danger.6" size="sm">{err}</Text>
            <Button size="compact-sm" variant="light" onClick={() => load()}>重試</Button>
          </Stack>
        )}
        {data && !busy && (
          <Stack gap="sm">
            <Group gap="xs">
              <Badge color={risk.color} variant="light">{risk.label}</Badge>
              {data.cached && <Text size="xs" c="dimmed">（快取）</Text>}
            </Group>
            <Text size="sm" style={{ lineHeight: 1.7 }}>{data.summary || "（無總評）"}</Text>
            {(data.pros.length > 0 || data.cons.length > 0) && (
              <Grid>
                {data.pros.length > 0 && (
                  <Grid.Col span={6}>
                    <Text size="sm" fw={600} c="teal.5" mb={4}>優點</Text>
                    <List size="sm" spacing={4}>
                      {data.pros.map((p, i) => <List.Item key={i}>{p}</List.Item>)}
                    </List>
                  </Grid.Col>
                )}
                {data.cons.length > 0 && (
                  <Grid.Col span={6}>
                    <Text size="sm" fw={600} c="amber.5" mb={4}>缺點</Text>
                    <List size="sm" spacing={4}>
                      {data.cons.map((c, i) => <List.Item key={i}>{c}</List.Item>)}
                    </List>
                  </Grid.Col>
                )}
              </Grid>
            )}
            {data.salary_notes && (
              <div>
                <Text size="sm" fw={600} mb={2}>薪資觀察</Text>
                <Text size="sm" c="dark.1">{data.salary_notes}</Text>
              </div>
            )}
            {data.interview_notes && (
              <div>
                <Text size="sm" fw={600} mb={2}>面試觀察</Text>
                <Text size="sm" c="dark.1">{data.interview_notes}</Text>
              </div>
            )}
            <div>
              <Text size="sm" fw={600} mb={2}>來源</Text>
              {data.sources.length === 0 && <Text size="sm" c="dimmed">（無來源）</Text>}
              <Stack gap={2}>
                {data.sources.map((s, i) => (
                  <Anchor key={i} href={s.url} target="_blank" size="xs">
                    {s.title || s.url}
                  </Anchor>
                ))}
              </Stack>
            </div>
            <Group justify="space-between" mt="xs">
              <Text size="xs" c="dimmed">查於 {data.researched_at}</Text>
              <Button size="compact-xs" variant="subtle" onClick={() => load(true)}>
                重新查詢
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}
```

- [ ] **Step 3: 嵌入 Dashboard**（`Dashboard.tsx`）

檔頭加 `import ResearchButton from "./ResearchButton";`。四個清單各加一顆（放法一致：公司文字 Text 之後、同一個左側 Group 內）：

1. 面試列——左側 `<Text size="sm" truncate style={{ minWidth: 0, flex: 1 }}>…</Text>` 之後、右側 Group 之前插入 `<ResearchButton company={iv.company} />`
2. 誰看過我——左側 Group 內 `</Text>` 之後插入 `<ResearchButton company={v.company} />`
3. 我的應徵——左側 Group 內 `</Text>` 之後插入 `<ResearchButton company={a.company} />`
4. 訊息——左側 Group 內 `</Text>` 之後插入 `<ResearchButton company={m.company} />`

- [ ] **Step 4: 嵌入 JobRow**（`JobRow.tsx`）

檔頭加 `import ResearchButton from "./ResearchButton";`；title 那行的 Group 內、`<Text fw={600} size="sm" truncate>{job.title}</Text>` 之後插入 `<ResearchButton company={job.company} />`。

- [ ] **Step 5: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 零 TS 錯誤

- [ ] **Step 6: Commit**

```bash
git add src/api.ts src/ResearchButton.tsx src/Dashboard.tsx src/JobRow.tsx
git commit -m "feat(sentinel): ResearchButton——公司名旁一鍵查評價+Modal（SP9）"
```

---

### Task 6: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`

- [ ] **Step 1: 真機驗證（需使用者操作）**

`career-sentinel serve` 重啟 → Ctrl+F5：
1. 儀表板任一公司名旁點 🔍 → Modal loading（20–60 秒）→ 出現風險燈號＋總評＋優缺點＋來源連結
2. 關掉再開同公司 → 秒開（快取）＋「（快取）」標記
3. 「重新查詢」→ 重跑並更新「查於」時間
4. 對你面試中的 2–3 家公司實查看品質（來源是否真實可點）

- [ ] **Step 2: roadmap 收尾 + Commit**

SP9 表格列劃掉、✅ 區加摘要（含 spike 結論：哪個 provider 路徑可用）、review minors 記技術債區、更新日期。

```bash
git add docs/superpowers/career-sentinel-roadmap.md
git commit -m "docs(sentinel): SP9 公司評價完成（roadmap 收尾）"
```
