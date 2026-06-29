# career-sentinel SP3 — 履歷健檢 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 上傳履歷 PDF → 針對目標職位（+薪資）用 LLM 分析「優勢／待補強」，在 web 履歷健檢頁呈現；移植雲端 resume_diagnosis 到地端。

**Architecture:** 新增 `resume.py`（pypdf 解析）、`llm.py`（結構化 `parse_json`）、`diagnosis.py`（移植雲端 prompt + 診斷），`models` 加 `ResumeDiagnosis`/`ResumeState`、`store` 加 resume 單列表，`web/app.py` 加 `/api/resume/{upload,diagnose}` + `GET /api/resume`，前端引入 Tabs（儀表板/履歷健檢）+ `ResumePage`。

**Tech Stack:** Python 3.12+、Pydantic v2、pypdf、python-multipart、FastAPI、httpx、anthropic（Foundry）、React+Vite+Mantine+TanStack Query。

## Global Constraints

- `sentinel/` 獨立，**不 import/依賴** 雲端 `backend/`、`frontend/`（移植＝複製邏輯，非 import）；套件名 `career_sentinel`。
- PDF 用 `pypdf`、上傳用 `python-multipart`、`.txt` 直接 decode；不支援格式 raise `ValueError`。
- `llm.parse_json`：**provider-aware**。`config.llm_provider()` 依 `.env` 偵測：有 `FOUNDRY_API_KEY`→`"foundry"`、否則有 `LLM_API_KEY`→`"openai"`、否則 `""`。openai 走 httpx `chat/completions`+`json_object`；foundry 走 `anthropic` SDK 的 `AnthropicFoundry`（原生 Messages API）。兩路皆 `_extract_json`（去 markdown 圍欄、取首 `{` 到末 `}`）→ `model_cls.model_validate(json.loads(...))`。無任何 key → raise `RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")`。
- 新依賴 `anthropic`（給 Foundry）。`AnthropicFoundry` 僅在 foundry 路徑且 `client is None`（真機）時匯入；單元測試注入假 client、不需真 SDK。
- `ResumeDiagnosis(strengths, gaps)` 與 `ResumeState(resume_text, target_title, expected_salary, diagnosis)` **皆放 `models.py`**；`diagnosis.py` 從 models 匯入（避免循環）。
- API 錯誤：upload 不支援格式→400；diagnose 無履歷→400「請先上傳履歷」、無 key→400「請先設定 LLM_API_KEY」、LLM 失敗→500「健檢失敗，請重試」。
- `/api/resume/*` 用 `create_app` 的 `resolved_db`；後端只綁 127.0.0.1（沿用）。
- 前端頂部 Mantine Tabs：「儀表板」（現有 Dashboard）、「履歷健檢」。
- 驗證閘門：`cd sentinel && uv run pytest` 全綠；`cd sentinel/web/frontend && npm run build` 成功。
- Phase 1/2/SP1/SP2 既有測試不得回歸。

---

### Task 1: `ResumeDiagnosis`/`ResumeState` 模型 + store resume 表

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`
- Modify: `sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_resume_store.py`

**Interfaces:**
- Produces：
  - `models.ResumeDiagnosis(strengths: list[str], gaps: list[str])`
  - `models.ResumeState(resume_text: str, target_title: str, expected_salary: int | None, diagnosis: ResumeDiagnosis | None)`
  - `store.load_resume(conn) -> ResumeState`、`store.save_resume(conn, state: ResumeState) -> None`

- [ ] **Step 1: 寫失敗測試 `tests/test_resume_store.py`**

```python
from career_sentinel import store
from career_sentinel.models import ResumeDiagnosis, ResumeState


def test_load_resume_default_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_resume(conn) == ResumeState()


def test_save_and_load_resume_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_resume(conn, ResumeState(
        resume_text="我的履歷", target_title="後端工程師", expected_salary=60000,
        diagnosis=ResumeDiagnosis(strengths=["熟 Python"], gaps=["缺雲端"]),
    ))
    s = store.load_resume(conn)
    assert s.resume_text == "我的履歷"
    assert s.target_title == "後端工程師"
    assert s.expected_salary == 60000
    assert s.diagnosis.strengths == ["熟 Python"]
    assert s.diagnosis.gaps == ["缺雲端"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_resume_store.py -v`
Expected: FAIL（`ImportError`/`AttributeError`）。

- [ ] **Step 3: 在 `models.py` 末尾加兩個模型**

```python
class ResumeDiagnosis(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ResumeState(BaseModel):
    resume_text: str = ""
    target_title: str = ""
    expected_salary: int | None = None
    diagnosis: ResumeDiagnosis | None = None
```

- [ ] **Step 4: 在 `store.py` 加 resume 表與 load/save**

把 `store.py` 的 `from .models import ...` 那行加入 `ResumeState`（例如 `from .models import Application, Message, ResumeState, Settings, Snapshot, Viewer`）。

在 `_SCHEMA` 末尾（結尾 `"""` 之前）加：
```sql
CREATE TABLE IF NOT EXISTS resume (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
```

在 `store.py` 末尾加：
```python
def load_resume(conn: sqlite3.Connection) -> ResumeState:
    row = conn.execute("SELECT data FROM resume WHERE id = 1").fetchone()
    if not row:
        return ResumeState()
    return ResumeState.model_validate_json(row[0])


def save_resume(conn: sqlite3.Connection, state: ResumeState) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO resume (id, data) VALUES (1, ?)",
        (state.model_dump_json(),),
    )
    conn.commit()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_resume_store.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 6: 全測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS。

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_resume_store.py
git commit -m "feat(sentinel): ResumeDiagnosis/ResumeState 模型 + store resume 表"
```

---

### Task 2: `resume.parse_resume`（PDF/txt）

**Files:**
- Modify: `sentinel/pyproject.toml`
- Create: `sentinel/src/career_sentinel/resume.py`
- Test: `sentinel/tests/test_resume_parse.py`

**Interfaces:**
- Produces：`resume.parse_resume(filename: str, data: bytes) -> str`（PDF/txt；不支援 raise `ValueError`）。

- [ ] **Step 1: 在 `pyproject.toml` 的 dependencies 加 `pypdf`**

在 `dependencies` 陣列加一行 `"pypdf>=5.1",`（保留既有）。

- [ ] **Step 2: 寫失敗測試 `tests/test_resume_parse.py`**

```python
import pytest

from career_sentinel.resume import parse_resume


def test_parse_txt():
    assert parse_resume("r.txt", "我的履歷\n後端".encode("utf-8")) == "我的履歷\n後端"


def test_parse_unsupported_raises():
    with pytest.raises(ValueError):
        parse_resume("r.png", b"x")
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd sentinel && uv sync && uv run pytest tests/test_resume_parse.py -v`
Expected: FAIL（`ModuleNotFoundError: career_sentinel.resume`）。

- [ ] **Step 4: 實作 `resume.py`**

```python
from __future__ import annotations

import io


def parse_resume(filename: str, data: bytes) -> str:
    """依副檔名解析履歷檔，回純文字。支援 PDF / TXT。"""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _parse_pdf(data)
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore").strip()
    raise ValueError(f"不支援的履歷格式：{filename}（支援 PDF / TXT）")


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_resume_parse.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 6: Commit**

```bash
git add sentinel/pyproject.toml sentinel/uv.lock sentinel/src/career_sentinel/resume.py sentinel/tests/test_resume_parse.py
git commit -m "feat(sentinel): resume.parse_resume（pypdf 解析 PDF / txt）"
```

---

### Task 3: config provider 偵測 + provider-aware `llm.parse_json`

**Files:**
- Modify: `sentinel/pyproject.toml`（加 `anthropic`）
- Modify: `sentinel/src/career_sentinel/config.py`
- Create: `sentinel/src/career_sentinel/llm.py`
- Test: `sentinel/tests/test_llm_parse_json.py`

**Interfaces:**
- Consumes：`config.llm_settings`。
- Produces：
  - `config.FoundrySettings(api_key, base_url, model)`、`config.foundry_settings() -> FoundrySettings`、`config.llm_provider() -> str`（`"foundry"`/`"openai"`/`""`）
  - `llm.parse_json(prompt: str, model_cls, *, system: str | None = None, client=None) -> model_cls`（無任何 key raise `RuntimeError`）
  - `llm._extract_json(text: str) -> str`

- [ ] **Step 1: 在 `pyproject.toml` 加 `anthropic`**

在 `dependencies` 加一行 `"anthropic>=0.40",`（保留既有）。

- [ ] **Step 2: 在 `config.py` 加 Foundry 設定與 provider 偵測**

在 `config.py` 末尾加（沿用既有 `os`/`dataclass` 匯入）：

```python
@dataclass(frozen=True)
class FoundrySettings:
    api_key: str
    base_url: str
    model: str


def foundry_settings() -> FoundrySettings:
    return FoundrySettings(
        api_key=os.getenv("FOUNDRY_API_KEY", ""),
        base_url=os.getenv("FOUNDRY_BASE_URL", ""),
        model=os.getenv("FOUNDRY_MODEL", "claude-sonnet-4-6"),
    )


def llm_provider() -> str:
    """依 .env 偵測 LLM provider：有 FOUNDRY_API_KEY→foundry、否則有 LLM_API_KEY→openai、否則空。"""
    if os.getenv("FOUNDRY_API_KEY"):
        return "foundry"
    if os.getenv("LLM_API_KEY"):
        return "openai"
    return ""
```

- [ ] **Step 3: 寫失敗測試 `tests/test_llm_parse_json.py`**

```python
import pytest

from career_sentinel import config, llm
from career_sentinel.config import FoundrySettings, LlmSettings
from career_sentinel.models import ResumeDiagnosis


# ---- OpenAI 相容路徑 ----
class _OpenAIResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": '{"strengths":["A"],"gaps":["B"]}'}}]}


class _OpenAIClient:
    def __init__(self):
        self.captured = {}

    def post(self, url, **kw):
        self.captured["url"] = url
        self.captured["json"] = kw["json"]
        return _OpenAIResp()


# ---- Foundry（Anthropic Messages）路徑 ----
class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FoundryResp:
    def __init__(self, text):
        self.content = [_Block(text)]


class _FoundryClient:
    """模擬 anthropic AnthropicFoundry：client.messages.create(...)。"""

    def __init__(self):
        self.messages = self
        self.captured = {}

    def create(self, **kw):
        self.captured = kw
        return _FoundryResp('```json\n{"strengths":["F"],"gaps":["G"]}\n```')


def test_parse_json_no_provider_raises(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "")
    with pytest.raises(RuntimeError):
        llm.parse_json("p", ResumeDiagnosis)


def test_parse_json_openai_path(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "openai")
    monkeypatch.setattr(llm, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    fc = _OpenAIClient()
    out = llm.parse_json("p", ResumeDiagnosis, system="s", client=fc)
    assert out.strengths == ["A"] and out.gaps == ["B"]
    assert fc.captured["url"] == "https://x/v1/chat/completions"
    assert fc.captured["json"]["response_format"] == {"type": "json_object"}


def test_parse_json_foundry_path(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "foundry")
    monkeypatch.setattr(llm, "foundry_settings", lambda: FoundrySettings("k", "https://f/anthropic", "claude-sonnet-4-6"))
    fc = _FoundryClient()
    out = llm.parse_json("p", ResumeDiagnosis, system="s", client=fc)
    assert out.strengths == ["F"] and out.gaps == ["G"]  # 含 markdown 圍欄仍正確抽出
    assert fc.captured["model"] == "claude-sonnet-4-6"
```

- [ ] **Step 4: 跑測試確認失敗**

Run: `cd sentinel && uv sync && uv run pytest tests/test_llm_parse_json.py -v`
Expected: FAIL（`ModuleNotFoundError: career_sentinel.llm`）。

- [ ] **Step 5: 實作 `llm.py`（provider-aware）**

```python
from __future__ import annotations

import json
import re

import httpx

from .config import foundry_settings, llm_provider, llm_settings


def _extract_json(text: str) -> str:
    """去 markdown 圍欄、取第一個 { 到最後一個 }。"""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_json(prompt: str, model_cls, *, system: str | None = None, client=None):
    """要 JSON、驗進 Pydantic model_cls。依 provider 走 OpenAI 相容或 Foundry(Anthropic)。"""
    provider = llm_provider()
    if provider == "openai":
        return _openai_parse_json(prompt, model_cls, system, client)
    if provider == "foundry":
        return _foundry_parse_json(prompt, model_cls, system, client)
    raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")


def _openai_parse_json(prompt, model_cls, system, client):
    cfg = llm_settings()
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    http = client or httpx.Client(timeout=120)
    owns_client = client is None
    try:
        resp = http.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model,
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return model_cls.model_validate(json.loads(_extract_json(content)))
    finally:
        if owns_client:
            http.close()


def _foundry_parse_json(prompt, model_cls, system, client):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    sys_text = (system + "\n\n" if system else "") + "只輸出單一 JSON 物件，不要任何額外文字或 markdown。"
    resp = client.messages.create(
        model=fs.model,
        max_tokens=4096,
        system=sys_text,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return model_cls.model_validate(json.loads(_extract_json(text)))
```

- [ ] **Step 6: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_llm_parse_json.py -v`
Expected: PASS（3 passed）。

- [ ] **Step 7: 全測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS。

- [ ] **Step 8: Commit**

```bash
git add sentinel/pyproject.toml sentinel/uv.lock sentinel/src/career_sentinel/config.py sentinel/src/career_sentinel/llm.py sentinel/tests/test_llm_parse_json.py
git commit -m "feat(sentinel): provider-aware llm.parse_json（OpenAI 相容 + Azure Foundry/Anthropic）"
```

---

### Task 4: `diagnosis`（移植雲端診斷）

**Files:**
- Create: `sentinel/src/career_sentinel/diagnosis.py`
- Test: `sentinel/tests/test_diagnosis.py`

**Interfaces:**
- Consumes：`llm.parse_json`、`models.ResumeDiagnosis`。
- Produces：`diagnosis.build_prompt(resume_text, target_title, expected_salary) -> str`、`diagnosis.diagnose(resume_text, target_title, expected_salary, *, client=None) -> ResumeDiagnosis`。

- [ ] **Step 1: 寫失敗測試 `tests/test_diagnosis.py`**

```python
from career_sentinel import diagnosis, llm
from career_sentinel.config import LlmSettings


def test_build_prompt_contains_target_and_resume():
    p = diagnosis.build_prompt("我會 Python", "後端工程師", 60000)
    assert "後端工程師" in p
    assert "我會 Python" in p
    assert "60000" in p


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": '{"strengths":["熟 Python"],"gaps":["缺雲端"]}'}}]}


class _FakeClient:
    def post(self, url, **kw):
        return _FakeResp()


def test_diagnose_with_fake_client(monkeypatch):
    # config 會載入 .env，實際 provider 可能是 foundry；測試固定走 openai 路徑 + 假 client
    monkeypatch.setattr(llm, "llm_provider", lambda: "openai")
    monkeypatch.setattr(llm, "llm_settings", lambda: LlmSettings("https://x/v1", "key", "m"))
    out = diagnosis.diagnose("我會 Python", "後端工程師", 60000, client=_FakeClient())
    assert out.strengths == ["熟 Python"]
    assert out.gaps == ["缺雲端"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_diagnosis.py -v`
Expected: FAIL（`ModuleNotFoundError`）。

- [ ] **Step 3: 實作 `diagnosis.py`**

```python
from __future__ import annotations

from . import llm
from .models import ResumeDiagnosis

_SYSTEM = "你是一位專業的求職顧問，請針對指定職位客觀分析履歷的優勢與待補強之處。"


def build_prompt(resume_text: str, target_title: str, expected_salary: int | None) -> str:
    return (
        f"目標職位：{target_title}\n"
        f"期望月薪：{expected_salary or '未指定'}\n\n"
        f"履歷內容：\n{resume_text}\n\n"
        "請針對『這個職位 + 這個薪資』分析這份履歷的『優勢』與『待補強』。"
        '只回 JSON，格式 {"strengths": ["..."], "gaps": ["..."]}。'
    )


def diagnose(resume_text: str, target_title: str, expected_salary: int | None, *, client=None) -> ResumeDiagnosis:
    return llm.parse_json(
        build_prompt(resume_text, target_title, expected_salary),
        ResumeDiagnosis,
        system=_SYSTEM,
        client=client,
    )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_diagnosis.py -v`
Expected: PASS（2 passed）。

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/diagnosis.py sentinel/tests/test_diagnosis.py
git commit -m "feat(sentinel): diagnosis（移植雲端履歷診斷 prompt + diagnose）"
```

---

### Task 5: API `/api/resume/{upload,diagnose}` + `GET /api/resume`

**Files:**
- Modify: `sentinel/pyproject.toml`（加 `python-multipart`）
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_resume.py`

**Interfaces:**
- Consumes：`resume.parse_resume`、`diagnosis.diagnose`、`store.{load_resume,save_resume}`、`models.{ResumeState,ResumeDiagnosis}`。
- Produces：三個 `/api/resume*` 端點。

- [ ] **Step 1: 在 `pyproject.toml` 加 `python-multipart`**

在 `dependencies` 加一行 `"python-multipart>=0.0.9",`（FastAPI `UploadFile` 需要）。

- [ ] **Step 2: 寫失敗測試 `tests/test_web_resume.py`**

```python
from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp
from career_sentinel.models import ResumeDiagnosis


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_resume_get_default(tmp_path):
    body = _client(tmp_path).get("/api/resume").json()
    assert body["has_resume"] is False
    assert body["chars"] == 0
    assert body["diagnosis"] is None


def test_resume_upload_txt(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/resume/upload", files={"file": ("r.txt", "我的履歷後端".encode("utf-8"), "text/plain")})
    assert r.status_code == 200
    assert r.json()["chars"] == len("我的履歷後端")
    assert c.get("/api/resume").json()["has_resume"] is True


def test_resume_diagnose_no_resume_400(tmp_path):
    r = _client(tmp_path).post("/api/resume/diagnose", json={"target_title": "後端", "expected_salary": None})
    assert r.status_code == 400


def test_resume_diagnose_success(tmp_path, monkeypatch):
    from career_sentinel import diagnosis
    monkeypatch.setattr(diagnosis, "diagnose", lambda text, title, sal, **kw: ResumeDiagnosis(strengths=["A"], gaps=["B"]))
    c = _client(tmp_path)
    c.post("/api/resume/upload", files={"file": ("r.txt", "履歷".encode("utf-8"), "text/plain")})
    r = c.post("/api/resume/diagnose", json={"target_title": "後端工程師", "expected_salary": 60000})
    assert r.status_code == 200
    assert r.json()["strengths"] == ["A"]
    g = c.get("/api/resume").json()
    assert g["target_title"] == "後端工程師"
    assert g["diagnosis"]["gaps"] == ["B"]
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd sentinel && uv sync && uv run pytest tests/test_web_resume.py -v`
Expected: FAIL（404 端點不存在）。

- [ ] **Step 4: 改 `web/app.py`**

在 `app.py` 頂端 import 區補上：
```python
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import config, diagnosis, diff, digest, resume, store, watch
from ..models import ResumeState, Settings
```
（保留既有 `from . import runner`。`FastAPI` 原已匯入；把 `File/HTTPException/UploadFile` 併入同一行。）

在 `create_app` 內、settings 兩個路由之後、`return app`/靜態掛載之前，加入：
```python
    class _DiagnoseReq(BaseModel):
        target_title: str
        expected_salary: int | None = None

    @app.post("/api/resume/upload")
    async def resume_upload(file: UploadFile = File(...)) -> dict:
        data = await file.read()
        try:
            text = resume.parse_resume(file.filename or "resume", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        conn = _conn()
        state = store.load_resume(conn)
        state.resume_text = text
        store.save_resume(conn, state)
        return {"chars": len(text)}

    @app.post("/api/resume/diagnose")
    def resume_diagnose(req: _DiagnoseReq) -> dict:
        conn = _conn()
        state = store.load_resume(conn)
        if not state.resume_text.strip():
            raise HTTPException(status_code=400, detail="請先上傳履歷")
        try:
            result = diagnosis.diagnose(state.resume_text, req.target_title, req.expected_salary)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            raise HTTPException(status_code=500, detail="健檢失敗，請重試")
        state.target_title = req.target_title
        state.expected_salary = req.expected_salary
        state.diagnosis = result
        store.save_resume(conn, state)
        return result.model_dump()

    @app.get("/api/resume")
    def resume_get() -> dict:
        state = store.load_resume(_conn())
        return {
            "has_resume": bool(state.resume_text.strip()),
            "chars": len(state.resume_text),
            "target_title": state.target_title,
            "expected_salary": state.expected_salary,
            "diagnosis": state.diagnosis.model_dump() if state.diagnosis else None,
        }
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_web_resume.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 6: 全測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全 PASS。

- [ ] **Step 7: Commit**

```bash
git add sentinel/pyproject.toml sentinel/uv.lock sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_resume.py
git commit -m "feat(sentinel): /api/resume upload·diagnose·GET（履歷健檢端點）"
```

---

### Task 6: 前端 Tabs + 履歷健檢頁

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`
- Modify: `sentinel/web/frontend/src/main.tsx`
- Create: `sentinel/web/frontend/src/App.tsx`
- Create: `sentinel/web/frontend/src/ResumePage.tsx`

**Interfaces:**
- Consumes：`/api/resume`（GET）、`/api/resume/upload`、`/api/resume/diagnose`。
- Produces：可 build 的 Tabs（儀表板/履歷健檢）+ ResumePage。

- [ ] **Step 1: 在 `src/api.ts` 末尾加 resume 型別與函式**

```ts
export interface ResumeDiagnosis { strengths: string[]; gaps: string[] }
export interface ResumeState {
  has_resume: boolean;
  chars: number;
  target_title: string;
  expected_salary: number | null;
  diagnosis: ResumeDiagnosis | null;
}

export async function getResume(): Promise<ResumeState> {
  const r = await fetch("/api/resume");
  return r.json();
}

export async function uploadResume(file: File): Promise<Response> {
  const fd = new FormData();
  fd.append("file", file);
  return fetch("/api/resume/upload", { method: "POST", body: fd });
}

export async function diagnoseResume(target_title: string, expected_salary: number | null): Promise<Response> {
  return fetch("/api/resume/diagnose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_title, expected_salary }),
  });
}
```

- [ ] **Step 2: 建立 `src/ResumePage.tsx`**

```tsx
import { Button, Container, FileInput, List, NumberInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { diagnoseResume, getResume, uploadResume } from "./api";

export default function ResumePage() {
  const qc = useQueryClient();
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (resume.data) {
      setTitle(resume.data.target_title);
      setSalary(resume.data.expected_salary ?? "");
    }
  }, [resume.data]);

  async function onUpload(file: File | null) {
    if (!file) return;
    setErr(null);
    const r = await uploadResume(file);
    if (!r.ok) { setErr("履歷上傳失敗（僅支援 PDF / TXT）"); return; }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  async function runDiagnose() {
    setErr(null);
    setBusy(true);
    const r = await diagnoseResume(title, salary === "" ? null : Number(salary));
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "健檢失敗");
      return;
    }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  const d = resume.data?.diagnosis;
  return (
    <Container size="md" py="lg">
      <Title order={2} mb="md">履歷健檢</Title>
      <Stack>
        <FileInput label="上傳履歷（PDF / TXT）" placeholder="選擇檔案" accept=".pdf,.txt" onChange={onUpload} />
        <Text size="sm" c="dimmed">{resume.data?.has_resume ? `已載入 ${resume.data.chars} 字` : "尚未上傳履歷"}</Text>
        <TextInput label="目標職稱" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
        <NumberInput label="期望月薪（選填）" value={salary} onChange={(v) => setSalary(typeof v === "number" ? v : "")} />
        {err && <Text c="red" size="sm">{err}</Text>}
        <Button onClick={runDiagnose} loading={busy} disabled={!resume.data?.has_resume || !title.trim()}>執行健檢</Button>
        {d && (
          <>
            <Title order={4} mt="md">優勢</Title>
            <List>{d.strengths.map((s, i) => <List.Item key={i}>✓ {s}</List.Item>)}</List>
            <Title order={4} mt="md">待補強</Title>
            <List>{d.gaps.map((g, i) => <List.Item key={i}>! {g}</List.Item>)}</List>
          </>
        )}
      </Stack>
    </Container>
  );
}
```

- [ ] **Step 3: 建立 `src/App.tsx`（Tabs）**

```tsx
import { Tabs } from "@mantine/core";
import Dashboard from "./Dashboard";
import ResumePage from "./ResumePage";

export default function App() {
  return (
    <Tabs defaultValue="dashboard" keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
    </Tabs>
  );
}
```

- [ ] **Step 4: 改 `src/main.tsx` 渲染 `<App/>`**

把 `import Dashboard from "./Dashboard";` 改為 `import App from "./App";`，並把 JSX 裡的 `<Dashboard />` 改為 `<App />`（其餘 MantineProvider/QueryClientProvider 不變）。

- [ ] **Step 5: 建置（閘門）**

Run: `cd sentinel/web/frontend && npm run build`
Expected: `tsc -b && vite build` 無型別錯誤、`✓ built`、產出 `dist/`。
若 `NumberInput` 的 `value`/`onChange` 型別報錯，依錯誤訊息最小調整（不改 API 合約）。

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/main.tsx sentinel/web/frontend/src/App.tsx sentinel/web/frontend/src/ResumePage.tsx
git commit -m "feat(sentinel): 前端 Tabs（儀表板/履歷健檢）+ 履歷健檢頁"
```

---

### Task 7: 真機整合驗證（控制器）

**Files:** 無（驗證任務）

- [ ] **Step 1: 全測試 + 前端建置**

Run: `cd sentinel && uv run pytest -q && cd web/frontend && npm run build`
Expected: pytest 全綠、build 成功。

- [ ] **Step 2: 真機端點驗證（控制器，serve + httpx）**

`career-sentinel serve` 背景起，然後：
- `GET /api/resume` → `has_resume: false`。
- `POST /api/resume/upload`（用一個小 `.txt` 或真實 PDF bytes）→ `{chars>0}`；再 `GET /api/resume` → `has_resume: true`。
- `POST /api/resume/diagnose`（`.env` 已設 `FOUNDRY_API_KEY` → provider=foundry，會真打 Azure Foundry/Claude）：
  - 預期 200 回 `{strengths, gaps}`，且 `GET /api/resume` 帶出 diagnosis。**這是驗證 Foundry 整合**（`AnthropicFoundry` 真實匯入 + 呼叫 + `_extract_json` 解析）的關鍵步驟。
  - 若 Foundry 端點/SDK 有問題（匯入失敗、base_url、回應格式）→ 在此暴露；控制器記錄並排除（必要時調 `_foundry_parse_json`）。
- 用真實 PDF 確認 `parse_resume` 的 PDF 抽取可用（pypdf）。

- [ ] **Step 3: 人工目視（使用者）**

`career-sentinel serve` → 切到「履歷健檢」分頁 → 上傳真實履歷 PDF → 填目標職稱 → 執行健檢
（需 `.env` 設 `LLM_API_KEY`）→ 看到優勢/待補強。

- [ ] **Step 4: Commit（里程碑）**

```bash
git commit --allow-empty -m "test(sentinel): SP3 全測試 + 前端建置 + 真機履歷健檢驗證"
```

---

## 完成後

履歷健檢可上傳 PDF、針對目標職位產出優勢/待補強。`llm.parse_json` 供 SP4（JD × 履歷比對）重用。見路線圖。
