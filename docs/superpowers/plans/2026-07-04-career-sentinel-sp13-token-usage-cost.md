# career-sentinel SP13：Token 用量與花費追蹤 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 側欄左下角常駐顯示累計 token 用量與預估 USD，並以 `usage_log` 表逐功能記錄每次 LLM 呼叫的 input/output/cache token 與換算成本，可看明細、可歸零。

**Architecture:** 新 `usage.py`（定價表＋成本換算＋兩家 provider usage 正規化＋best-effort 寫入＋summary/reset）；`store.py` `_SCHEMA` 加 `usage_log` 表。所有 LLM 出口（`llm.parse_json`/`chat_stream`、`chat.stream_with_tools`、`research`、`digest`）加 `feature` 標籤、回應拿到後 `usage.record(feature, model, raw)`（全程 try/except、絕不影響 LLM 呼叫）。`GET/DELETE /api/usage` 純本地 DB。前端側欄底部 `UsageBadge`（TanStack Query 30 秒輪詢）＋點開 Modal 明細＋歸零。

**Tech Stack:** Python 3.12、SQLite（`sqlite3`）、FastAPI、Pydantic v2；React 18＋Mantine 7＋TanStack Query＋Vite；測試 pytest（`uv run pytest`）。

## Global Constraints

- **記帳 best-effort、絕不影響既有行為**：`usage.record` 全程包 try/except，任何例外（含 DB lock、normalize 失敗）都不得往上冒到 LLM 呼叫；所有 LLM 函式的既有回傳值/yield 行為一字不改。
- **涵蓋所有 LLM 出口**才不會誤導——非串流（parse_json/research/digest）與串流（chat_stream/stream_with_tools）都要插樁。
- **定價寫在 `_PRICING` 常數、可調**，預設套 Claude Sonnet 4.5 官方單價（input 3.00 / output 15.00 / cache_write 3.75 / cache_read 0.30，$/M tokens）。Foundry 實際計費可能不同，是已知取捨。
- **OpenAI 的 `prompt_tokens` 含 cache**（`input = prompt_tokens - cached`）；**Anthropic 的 `input_tokens` 不含 cache**（直接對應 `input`）。
- `usage.record` 自開連線 `store.connect(db or config.db_path())`；`summary`/`reset` 收 conn 參數。
- 端點回傳、feature 字串為**繁體中文常數**：履歷健檢／JD比對／客製化／整理助手／公司研究／每日彙整。
- `.superpowers/sdd/progress.md` 是 gitignored——**不要 git add**。
- 不要動 `main`；合併與部署由使用者指示（main push 觸發自動部署）。

---

### Task 1：`usage.py` 核心 + `usage_log` 表

**Files:**
- Create: `sentinel/src/career_sentinel/usage.py`
- Modify: `sentinel/src/career_sentinel/store.py`（`_SCHEMA` 末尾加表）
- Test: `sentinel/tests/test_usage.py`

**Interfaces:**
- Produces:
  - `usage.cost_of(model: str, input_tokens: int, output_tokens: int, cache_read: int, cache_write: int) -> float`
  - `usage.normalize(raw) -> dict`（鍵 `input`/`output`/`cache_read`/`cache_write`，皆 int）
  - `usage.record(feature: str, model: str, raw, *, db=None) -> None`（best-effort）
  - `usage.summary(conn) -> dict`（`{"total_tokens", "total_usd", "by_feature": [{"feature","calls","tokens","usd"}]}`，by_feature 依 usd 降冪）
  - `usage.reset(conn) -> None`
  - `usage._price_for(model: str) -> dict`
- Consumes: `store.connect(path)`（現有）、`config.db_path()`（現有）。

- [ ] **Step 1: 寫失敗測試**

Create `sentinel/tests/test_usage.py`：

```python
from types import SimpleNamespace

from career_sentinel import store, usage


def test_price_for_sonnet_and_default():
    assert usage._price_for("claude-sonnet-4-5")["in"] == 3.00
    assert usage._price_for("some-unknown-model") == usage._PRICING["default"]


def test_cost_of_known_tokens():
    # 1M input @3, 1M output @15, 1M cache_read @0.30, 1M cache_write @3.75
    cost = usage.cost_of("sonnet", 1_000_000, 1_000_000, 1_000_000, 1_000_000)
    assert abs(cost - (3.00 + 15.00 + 0.30 + 3.75)) < 1e-9


def test_normalize_anthropic_object():
    raw = SimpleNamespace(
        input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=20, cache_read_input_tokens=10,
    )
    assert usage.normalize(raw) == {"input": 100, "output": 50, "cache_read": 10, "cache_write": 20}


def test_normalize_openai_dict_with_cache():
    raw = {"prompt_tokens": 100, "completion_tokens": 40,
           "prompt_tokens_details": {"cached_tokens": 30}}
    # OpenAI prompt_tokens 含 cache：input = 100 - 30
    assert usage.normalize(raw) == {"input": 70, "output": 40, "cache_read": 30, "cache_write": 0}


def test_normalize_openai_dict_no_cache():
    raw = {"prompt_tokens": 80, "completion_tokens": 20}
    assert usage.normalize(raw) == {"input": 80, "output": 20, "cache_read": 0, "cache_write": 0}


def test_normalize_none():
    assert usage.normalize(None) == {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def test_record_summary_reset_roundtrip(tmp_path):
    db = tmp_path / "u.db"
    usage.record("履歷健檢", "claude-sonnet-4-5",
                 SimpleNamespace(input_tokens=1_000_000, output_tokens=0,
                                 cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    usage.record("JD比對", "claude-sonnet-4-5",
                 SimpleNamespace(input_tokens=0, output_tokens=1_000_000,
                                 cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    usage.record("JD比對", "claude-sonnet-4-5",
                 SimpleNamespace(input_tokens=1_000_000, output_tokens=0,
                                 cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    conn = store.connect(db)
    s = usage.summary(conn)
    assert s["total_tokens"] == 3_000_000
    assert abs(s["total_usd"] - (3.00 + 15.00 + 3.00)) < 1e-9
    # by_feature 依 usd 降冪：JD比對(18.0, 2 次) 在 履歷健檢(3.0, 1 次) 前
    assert [f["feature"] for f in s["by_feature"]] == ["JD比對", "履歷健檢"]
    assert s["by_feature"][0]["calls"] == 2
    usage.reset(conn)
    assert usage.summary(conn)["total_tokens"] == 0
    conn.close()


def test_record_best_effort_swallows(monkeypatch, tmp_path):
    def boom(_raw):
        raise ValueError("boom")
    monkeypatch.setattr(usage, "normalize", boom)
    # 不得往上拋
    usage.record("x", "m", object(), db=tmp_path / "u.db")
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_usage.py -q`
Expected: FAIL（`ModuleNotFoundError: career_sentinel.usage` 或屬性不存在）

- [ ] **Step 3: `store.py` `_SCHEMA` 末尾（`company_research` 之後、閉合 `"""` 之前）加表**

在 `sentinel/src/career_sentinel/store.py` 的 `_SCHEMA` 字串內，`company_research` 表定義之後加：

```sql
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    at TEXT NOT NULL
);
```

- [ ] **Step 4: 建 `usage.py`**

Create `sentinel/src/career_sentinel/usage.py`：

```python
"""SP13：LLM token 用量與花費記錄。best-effort，絕不影響 LLM 呼叫。"""
from __future__ import annotations

from datetime import datetime

from . import config, store

# $/M tokens。預設套 Claude Sonnet 4.5 官方單價（Foundry 實際計費可能不同、此表可調）。
_PRICING: dict[str, dict[str, float]] = {
    "sonnet": {"in": 3.00, "out": 15.00, "cache_read": 0.30, "cache_write": 3.75},
    "default": {"in": 3.00, "out": 15.00, "cache_read": 0.30, "cache_write": 3.75},
}


def _price_for(model: str) -> dict[str, float]:
    m = (model or "").lower()
    for key, price in _PRICING.items():
        if key != "default" and key in m:
            return price
    return _PRICING["default"]


def cost_of(model: str, input_tokens: int, output_tokens: int,
            cache_read: int, cache_write: int) -> float:
    p = _price_for(model)
    return (
        input_tokens * p["in"]
        + output_tokens * p["out"]
        + cache_read * p["cache_read"]
        + cache_write * p["cache_write"]
    ) / 1_000_000


def _get(raw, name):
    if isinstance(raw, dict):
        return raw.get(name)
    return getattr(raw, name, None)


def normalize(raw) -> dict:
    """兩家 provider 的 usage 正規化成 input/output/cache_read/cache_write（int）。"""
    if raw is None:
        return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    a_in = _get(raw, "input_tokens")
    if a_in is not None:  # Anthropic：input_tokens 不含 cache
        return {
            "input": int(a_in or 0),
            "output": int(_get(raw, "output_tokens") or 0),
            "cache_read": int(_get(raw, "cache_read_input_tokens") or 0),
            "cache_write": int(_get(raw, "cache_creation_input_tokens") or 0),
        }
    prompt = _get(raw, "prompt_tokens")
    if prompt is not None:  # OpenAI：prompt_tokens 含 cache
        details = _get(raw, "prompt_tokens_details")
        if isinstance(details, dict):
            cached = details.get("cached_tokens") or 0
        else:
            cached = getattr(details, "cached_tokens", 0) or 0
        cached = int(cached)
        return {
            "input": max(int(prompt) - cached, 0),
            "output": int(_get(raw, "completion_tokens") or 0),
            "cache_read": cached,
            "cache_write": 0,
        }
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


def record(feature: str, model: str, raw, *, db=None) -> None:
    """記一列 usage_log。best-effort：任何例外都吞掉，絕不影響 LLM 呼叫。"""
    try:
        n = normalize(raw)
        cost = cost_of(model, n["input"], n["output"], n["cache_read"], n["cache_write"])
        conn = store.connect(db or config.db_path())
        try:
            conn.execute(
                "INSERT INTO usage_log "
                "(feature, model, input_tokens, output_tokens, cache_read, cache_write, cost_usd, at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (feature, model or "", n["input"], n["output"], n["cache_read"],
                 n["cache_write"], cost, datetime.now().isoformat(timespec="seconds")),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 — 記帳絕不影響主流程
        pass


def summary(conn) -> dict:
    total_tokens = conn.execute(
        "SELECT COALESCE(SUM(input_tokens+output_tokens+cache_read+cache_write),0) FROM usage_log"
    ).fetchone()[0]
    total_usd = conn.execute("SELECT COALESCE(SUM(cost_usd),0) FROM usage_log").fetchone()[0]
    rows = conn.execute(
        "SELECT feature, COUNT(*), "
        "COALESCE(SUM(input_tokens+output_tokens+cache_read+cache_write),0), "
        "COALESCE(SUM(cost_usd),0) "
        "FROM usage_log GROUP BY feature ORDER BY SUM(cost_usd) DESC"
    ).fetchall()
    by_feature = [
        {"feature": r[0], "calls": int(r[1]), "tokens": int(r[2]), "usd": float(r[3])}
        for r in rows
    ]
    return {"total_tokens": int(total_tokens), "total_usd": float(total_usd), "by_feature": by_feature}


def reset(conn) -> None:
    conn.execute("DELETE FROM usage_log")
    conn.commit()
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_usage.py -q`
Expected: PASS（8 passed）

- [ ] **Step 6: 全測試回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（既有 240 + 新增）

- [ ] **Step 7: Commit**

```bash
git add sentinel/src/career_sentinel/usage.py sentinel/src/career_sentinel/store.py sentinel/tests/test_usage.py
git commit -m "feat(sentinel): usage 記錄核心 + usage_log 表（SP13）"
```

---

### Task 2：插樁非串流 LLM 出口（parse_json / research / digest）

**Files:**
- Modify: `sentinel/src/career_sentinel/llm.py`（`parse_json`、`_openai_parse_json`、`_foundry_parse_json`）
- Modify: `sentinel/src/career_sentinel/research.py`（`research_company`、`_openai_research`、`_foundry_research`）
- Modify: `sentinel/src/career_sentinel/digest.py`（`summarize`）
- Modify: `sentinel/src/career_sentinel/diagnosis.py`、`match.py`、`tailor.py`、`chat.py`（呼叫端傳 `feature`）
- Test: `sentinel/tests/test_usage_instrument.py`

**Interfaces:**
- Consumes: `usage.record(feature, model, raw, *, db=None)`（Task 1）。
- Produces（供 Task 3 與呼叫端沿用）：
  - `llm.parse_json(prompt, model_cls, *, system=None, client=None, feature="")`
  - `research.research_company(name, *, client=None, feature="公司研究")`
  - `digest.summarize(diff, snapshot, *, client=None)`（feature 內部常數 `"每日彙整"`）

- [ ] **Step 1: 寫失敗測試**

Create `sentinel/tests/test_usage_instrument.py`：

```python
from types import SimpleNamespace

from career_sentinel import diagnosis, llm, usage
from career_sentinel.models import ResumeDiagnosis


class _FakeFoundry:
    """假 AnthropicFoundry：messages.create 回帶 usage 的假 resp。"""
    def __init__(self, text, usage_obj):
        self._text = text
        self._usage = usage_obj
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=self._text)],
            usage=self._usage,
        )


def test_parse_json_foundry_records_usage(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "foundry")
    monkeypatch.setattr(llm, "foundry_settings",
                        lambda: SimpleNamespace(api_key="k", base_url="b", model="claude-sonnet-4-5"))
    captured = {}
    monkeypatch.setattr(usage, "record",
                        lambda feature, model, raw, **kw: captured.update(
                            feature=feature, model=model, raw=raw))
    fake = _FakeFoundry('{"strengths": ["a"], "gaps": ["b"]}',
                        SimpleNamespace(input_tokens=10, output_tokens=5,
                                        cache_creation_input_tokens=0, cache_read_input_tokens=0))
    out = diagnosis.diagnose("履歷", "工程師", None, client=fake)
    assert isinstance(out, ResumeDiagnosis)          # 回傳值不變
    assert out.strengths == ["a"]
    assert captured["feature"] == "履歷健檢"           # feature 正確
    assert captured["model"] == "claude-sonnet-4-5"   # model 正確
    assert captured["raw"].input_tokens == 10
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_usage_instrument.py -q`
Expected: FAIL（`usage.record` 未被呼叫 / `parse_json` 無 `feature` 參數）

- [ ] **Step 3: 改 `llm.py`**

`parse_json` 加 `feature` 參數並下傳：

```python
def parse_json(prompt: str, model_cls, *, system: str | None = None, client=None, feature: str = ""):
    """要 JSON、驗進 Pydantic model_cls。依 provider 走 OpenAI 相容或 Foundry(Anthropic)。"""
    system = _with_today(system)
    provider = llm_provider()
    if provider == "openai":
        return _openai_parse_json(prompt, model_cls, system, client, feature)
    if provider == "foundry":
        return _foundry_parse_json(prompt, model_cls, system, client, feature)
    raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
```

檔案頂端 import 區加 `from . import usage`（與現有 `from .config import ...` 並列）。

`_openai_parse_json` 收 `feature`、拿 usage：

```python
def _openai_parse_json(prompt, model_cls, system, client, feature):
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
        data = resp.json()
        usage.record(feature, cfg.model, data.get("usage"))
        content = data["choices"][0]["message"]["content"]
        return model_cls.model_validate(json.loads(_extract_json(content)))
    finally:
        if owns_client:
            http.close()
```

`_foundry_parse_json` 收 `feature`、拿 usage：

```python
def _foundry_parse_json(prompt, model_cls, system, client, feature):
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
    usage.record(feature, fs.model, getattr(resp, "usage", None))
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return model_cls.model_validate(json.loads(_extract_json(text)))
```

> 註：測試 monkeypatch 了 `llm.llm_provider`/`llm.foundry_settings`，因為它們是 `llm` 模組層級名稱（`from .config import foundry_settings, llm_provider, llm_settings`）——沿用既有 import 慣例，勿改成 `config.llm_provider`。

- [ ] **Step 4: 改 `diagnosis.py` / `match.py` / `tailor.py` / `chat.py` 傳 feature**

`diagnosis.py` `diagnose` 內 `llm.parse_json(...)` 加 `feature="履歷健檢"`：

```python
    return llm.parse_json(
        build_prompt(resume_text, target_title, expected_salary),
        ResumeDiagnosis,
        system=_SYSTEM,
        client=client,
        feature="履歷健檢",
    )
```

`match.py` `match` 內 `llm.parse_json(...)` 加 `feature="JD比對"`：

```python
    return llm.parse_json(
        build_prompt(resume_text, target_title, jd),
        MatchResult,
        system=_SYSTEM,
        client=client,
        feature="JD比對",
    )
```

`tailor.py` `tailor_application` 內 `llm.parse_json(...)` 加 `feature="客製化"`：

```python
    result = llm.parse_json(
        build_prompt(resume_text, target_title, jd),
        TailoredApplication,
        system=_SYSTEM,
        client=client,
        feature="客製化",
    )
```

`chat.py` `maybe_curate_memory` 內 `llm.parse_json(prompt, CuratedFacts)` 改為：

```python
        curated = llm.parse_json(prompt, CuratedFacts, feature="整理助手")
```

- [ ] **Step 5: 改 `research.py`**

檔案頂端 import 區加 `from . import usage`（與現有 `from . import llm` 並列）。
`research_company` 加 `feature` 參數並下傳；私有函式收 `feature` 記 usage：

```python
def research_company(name: str, *, client=None, feature: str = "公司研究") -> CompanyResearch:
    provider = llm_provider()
    prompt = build_research_prompt(name)
    if provider == "openai":
        text = _openai_research(prompt, client, feature)
    elif provider == "foundry":
        text = _foundry_research(prompt, client, feature)
    else:
        raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
    r = CompanyResearch.model_validate(json.loads(llm._extract_json(text)))
    r.company = name
    r.researched_at = datetime.now().isoformat(timespec="seconds")
    return r


def _openai_research(prompt, client, feature):
    cfg = llm_settings()
    http = client or httpx.Client(timeout=_TIMEOUT)
    owns_client = client is None
    try:
        resp = http.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model + ":online",
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage.record(feature, cfg.model, data.get("usage"))
        return data["choices"][0]["message"]["content"]
    finally:
        if owns_client:
            http.close()


def _foundry_research(prompt, client, feature):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url, timeout=_TIMEOUT)
    resp = client.messages.create(
        model=fs.model,
        max_tokens=4096,
        tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        messages=[{"role": "user", "content": prompt}],
    )
    usage.record(feature, fs.model, getattr(resp, "usage", None))
    return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
```

- [ ] **Step 6: 改 `digest.py` `summarize`**

檔案頂端 import 區加 `from . import usage`。`summarize` 內記 usage（feature 常數 `"每日彙整"`）——只改「成功回傳」那段，例外/fallback 不動：

```python
def summarize(diff: Diff, snapshot: Snapshot, *, client: object | None = None) -> str:
    cfg = llm_settings()
    if diff.is_empty() or not cfg.api_key:
        return _local_fallback(diff, snapshot)

    http = client or httpx.Client(timeout=60)
    owns_client = client is None
    try:
        resp = http.post(
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={
                "model": cfg.model,
                "messages": [{"role": "user", "content": build_prompt(diff, snapshot)}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        usage.record("每日彙整", cfg.model, data.get("usage"))
        return data["choices"][0]["message"]["content"]
    except Exception:
        return "（今日彙整暫無）\n" + render_human(diff, snapshot)
    finally:
        if owns_client:
            http.close()
```

- [ ] **Step 7: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_usage_instrument.py -q`
Expected: PASS

- [ ] **Step 8: 全測試回歸（確認既有 LLM 測試零回歸）**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/llm.py sentinel/src/career_sentinel/research.py sentinel/src/career_sentinel/digest.py sentinel/src/career_sentinel/diagnosis.py sentinel/src/career_sentinel/match.py sentinel/src/career_sentinel/tailor.py sentinel/src/career_sentinel/chat.py sentinel/tests/test_usage_instrument.py
git commit -m "feat(sentinel): 插樁非串流 LLM 出口記 usage（parse_json/research/digest）（SP13）"
```

---

### Task 3：插樁串流 LLM 出口（chat_stream / stream_with_tools）

**Files:**
- Modify: `sentinel/src/career_sentinel/llm.py`（`chat_stream`、`_openai_chat_stream`、`_foundry_chat_stream`）
- Modify: `sentinel/src/career_sentinel/chat.py`（`stream_with_tools`、`maybe_compact`）
- Modify: `sentinel/src/career_sentinel/web/app.py`（chat 路由 `llm.chat_stream(...)` 傳 feature）
- Test: `sentinel/tests/test_usage_instrument.py`（append）

**Interfaces:**
- Consumes: `usage.record`（Task 1）。
- Produces:
  - `llm.chat_stream(messages, *, system=None, client=None, feature="")`
  - `chat.stream_with_tools(messages, *, system, client=None, feature="整理助手")`

- [ ] **Step 1: 追加失敗測試**（append 到 `tests/test_usage_instrument.py`）

```python
class _FakeStream:
    def __init__(self, chunks, final):
        self._chunks = chunks
        self._final = final
        self.text_stream = iter(chunks)
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    def get_final_message(self):
        return self._final


class _FakeFoundryStream:
    def __init__(self, chunks, final):
        self._stream = _FakeStream(chunks, final)
        self.messages = SimpleNamespace(stream=lambda **kw: self._stream)


def test_chat_stream_foundry_records_usage(monkeypatch):
    monkeypatch.setattr(llm, "llm_provider", lambda: "foundry")
    monkeypatch.setattr(llm, "foundry_settings",
                        lambda: SimpleNamespace(api_key="k", base_url="b", model="claude-sonnet-4-5"))
    captured = {}
    monkeypatch.setattr(usage, "record",
                        lambda feature, model, raw, **kw: captured.update(
                            feature=feature, model=model, raw=raw))
    final = SimpleNamespace(usage=SimpleNamespace(
        input_tokens=7, output_tokens=3,
        cache_creation_input_tokens=0, cache_read_input_tokens=0), stop_reason="end_turn")
    fake = _FakeFoundryStream(["你", "好"], final)
    out = "".join(llm.chat_stream([{"role": "user", "content": "hi"}],
                                  feature="整理助手", client=fake))
    assert out == "你好"                              # yield 行為不變
    assert captured["feature"] == "整理助手"
    assert captured["raw"].input_tokens == 7
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_usage_instrument.py::test_chat_stream_foundry_records_usage -q`
Expected: FAIL（`chat_stream` 無 `feature` 參數 / usage 未記）

- [ ] **Step 3: 改 `llm.py` `chat_stream`**

```python
def chat_stream(messages: list[dict], *, system: str | None = None, client=None, feature: str = ""):
    """多輪對話串流，yield 文字增量。依 provider 走 OpenAI 相容或 Foundry(Anthropic)。"""
    system = _with_today(system)
    provider = llm_provider()
    if provider == "openai":
        yield from _openai_chat_stream(messages, system, client, feature)
    elif provider == "foundry":
        yield from _foundry_chat_stream(messages, system, client, feature)
    else:
        raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
```

`_openai_chat_stream` 收 `feature`、加 `stream_options` 取 usage、末端記帳：

```python
def _openai_chat_stream(messages, system, client, feature):
    cfg = llm_settings()
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    http = client or httpx.Client(timeout=300)
    owns_client = client is None
    last_usage = None
    try:
        with http.stream(
            "POST",
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={"model": cfg.model, "messages": msgs, "stream": True,
                  "stream_options": {"include_usage": True}},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                data = json.loads(payload)
                if data.get("usage"):
                    last_usage = data["usage"]
                choices = data.get("choices") or []
                if not choices:
                    continue
                text = choices[0].get("delta", {}).get("content")
                if text:
                    yield text
        usage.record(feature, cfg.model, last_usage)
    finally:
        if owns_client:
            http.close()
```

`_foundry_chat_stream` 收 `feature`、串流耗盡後 `get_final_message().usage`：

```python
def _foundry_chat_stream(messages, system, client, feature):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    kwargs: dict = {"model": fs.model, "max_tokens": 4096, "messages": messages}
    if system:
        kwargs["system"] = system
    with client.messages.stream(**kwargs) as stream:
        yield from stream.text_stream
        final = stream.get_final_message()
    usage.record(feature, fs.model, getattr(final, "usage", None))
```

- [ ] **Step 4: 改 `chat.py`**

檔案頂端 import 區把 `from . import llm, store` 改成 `from . import llm, store, usage`。

`stream_with_tools` 加 `feature` 參數、每輪 `final` 後記帳：

```python
def stream_with_tools(messages: list[dict], *, system: str, client=None, feature: str = "整理助手"):
    """Foundry 原生 tool use 串流：yield {"type":"text"} 與 {"type":"jobs"} 事件。

    工具執行達 TOOL_LOOP_MAX 後，最後一輪不帶 tools 強制作答。
    """
    from .config import foundry_settings

    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url, timeout=180)
    system = llm._with_today(system)
    msgs = list(messages)
    tool_runs = 0
    for _ in range(TOOL_LOOP_MAX + 1):
        kwargs: dict = {
            "model": fs.model, "max_tokens": 4096,
            "system": system, "messages": msgs,
        }
        if tool_runs < TOOL_LOOP_MAX:
            kwargs["tools"] = TOOLS
        with client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield {"type": "text", "text": text}
            final = stream.get_final_message()
        usage.record(feature, fs.model, getattr(final, "usage", None))
        if final.stop_reason != "tool_use":
            return
        results = []
        for block in final.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            keyword = str((block.input or {}).get("keyword", ""))
            jobs, result_text, is_error = _execute_search(keyword)
            tool_runs += 1
            if not is_error:
                yield {"type": "jobs", "keyword": keyword, "items": jobs}
            entry = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            if is_error:
                entry["is_error"] = True
            results.append(entry)
        msgs = msgs + [
            {"role": "assistant", "content": final.content},
            {"role": "user", "content": results},
        ]
```

`maybe_compact` 內 `llm.chat_stream([...])` 傳 feature：

```python
        new_summary = "".join(llm.chat_stream(
            [{"role": "user", "content": prompt}], feature="整理助手"))
```

- [ ] **Step 5: 改 `web/app.py` chat 路由**

`app.py:48` 的 `llm.chat_stream(messages, system=system)` 改為：

```python
        for chunk in llm.chat_stream(messages, system=system, feature="整理助手"):
```

（`app.py:46` 的 `chatmod.stream_with_tools(messages, system=system)` 不需改，feature 預設 `"整理助手"`。）

- [ ] **Step 6: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_usage_instrument.py -q`
Expected: PASS

- [ ] **Step 7: 全測試回歸（含既有 chat/stream 測試零回歸）**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/llm.py sentinel/src/career_sentinel/chat.py sentinel/src/career_sentinel/web/app.py sentinel/tests/test_usage_instrument.py
git commit -m "feat(sentinel): 插樁串流 LLM 出口記 usage（chat_stream/stream_with_tools）（SP13）"
```

---

### Task 4：端點 `GET /api/usage` + `DELETE /api/usage`

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`（import + 兩個路由）
- Test: `sentinel/tests/test_web_app.py`（append）

**Interfaces:**
- Consumes: `usage.summary(conn)`、`usage.reset(conn)`（Task 1）；`_conn()`（app.py 現有）。
- Produces: `GET /api/usage` → summary dict；`DELETE /api/usage` → `{"status": "reset"}`。

- [ ] **Step 1: 追加失敗測試**（append 到 `sentinel/tests/test_web_app.py`）

> 先看該檔頂部既有的 app fixture/`TestClient` 建法（多以 `create_app(db_path=...)` + `fastapi.testclient.TestClient`）並沿用同一 pattern。以下用該檔既有的 client fixture 名（若為 `client`）：

```python
def test_get_usage_returns_summary(tmp_path):
    from fastapi.testclient import TestClient

    from career_sentinel import usage
    from career_sentinel.web.app import create_app

    db = tmp_path / "u.db"
    usage.record("履歷健檢", "claude-sonnet-4-5",
                 __import__("types").SimpleNamespace(
                     input_tokens=1_000_000, output_tokens=0,
                     cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    c = TestClient(create_app(db_path=str(db)))
    body = c.get("/api/usage").json()
    assert body["total_tokens"] == 1_000_000
    assert body["by_feature"][0]["feature"] == "履歷健檢"


def test_delete_usage_resets(tmp_path):
    from fastapi.testclient import TestClient

    from career_sentinel import usage
    from career_sentinel.web.app import create_app

    db = tmp_path / "u.db"
    usage.record("JD比對", "claude-sonnet-4-5",
                 __import__("types").SimpleNamespace(
                     input_tokens=1_000_000, output_tokens=0,
                     cache_creation_input_tokens=0, cache_read_input_tokens=0), db=db)
    c = TestClient(create_app(db_path=str(db)))
    assert c.delete("/api/usage").json() == {"status": "reset"}
    assert c.get("/api/usage").json()["total_tokens"] == 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -k usage -q`
Expected: FAIL（404，路由不存在）

- [ ] **Step 3: 改 `web/app.py`**

在 app.py 頂部 sibling import 區（與 `from .. import ... store` 等並列）加：

```python
from .. import usage as usagemod
```

在 `create_app` 內任一既有 `@app.get(...)` 附近加兩個路由（`_conn` 已於 `create_app` 內定義）：

```python
    @app.get("/api/usage")
    def usage_summary() -> dict:
        return usagemod.summary(_conn())

    @app.delete("/api/usage")
    def usage_reset() -> dict:
        usagemod.reset(_conn())
        return {"status": "reset"}
```

> 若 app.py 現有 import 是 `from career_sentinel import ...` 形式，改用相符形式（如 `from career_sentinel import usage as usagemod`），與該檔既有慣例一致即可。

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_web_app.py -k usage -q`
Expected: PASS

- [ ] **Step 5: 全測試回歸**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_app.py
git commit -m "feat(sentinel): /api/usage 讀取與歸零端點（SP13）"
```

---

### Task 5：前端側欄左下角 `UsageBadge` + 明細 Modal

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（介面 + `getUsage`/`resetUsage`）
- Modify: `sentinel/web/frontend/src/Sidebar.tsx`（底部加 `UsageBadge`）
- 建置驗證（無單元測試框架，走 `npm run build`）

**Interfaces:**
- Consumes: `GET /api/usage`、`DELETE /api/usage`（Task 4）。
- Produces: `api.getUsage()`、`api.resetUsage()`、`UsageSummary`/`UsageFeature`。

- [ ] **Step 1: `api.ts` 加介面與函式**（append 到檔案末尾）

```typescript
export interface UsageFeature { feature: string; calls: number; tokens: number; usd: number }
export interface UsageSummary { total_tokens: number; total_usd: number; by_feature: UsageFeature[] }

export async function getUsage(): Promise<UsageSummary> {
  const r = await fetch("/api/usage");
  return r.json();
}
export async function resetUsage(): Promise<Response> {
  return fetch("/api/usage", { method: "DELETE" });
}
```

- [ ] **Step 2: `Sidebar.tsx` 加 `UsageBadge` 元件與底部掛載**

改 import 行（第 1 行）——加 `Group`、`Modal`、`Table`、`UnstyledButton`：

```typescript
import { Button, Group, Modal, NavLink, Stack, Table, Text, UnstyledButton } from "@mantine/core";
```

第 2–5 行 icon import 加 `IconCoin`：

```typescript
import {
  IconArrowsExchange, IconCoin, IconFileText, IconId, IconLayoutDashboard, IconMessageCircle,
  IconRefresh, IconSearch, IconSettings, IconStars, IconWand,
} from "@tabler/icons-react";
```

新增 React/Query/hooks import（放在 icon import 之後）：

```typescript
import { useDisclosure } from "@mantine/hooks";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getUsage, resetUsage, type UsageSummary } from "./api";
```

在 `export default function Sidebar` 之前加 `UsageBadge` 元件與格式化 helper：

```typescript
function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function UsageBadge() {
  const [opened, { open, close }] = useDisclosure(false);
  const qc = useQueryClient();
  const { data } = useQuery<UsageSummary>({
    queryKey: ["usage"],
    queryFn: getUsage,
    refetchInterval: 30000,
  });
  const total = data ?? { total_tokens: 0, total_usd: 0, by_feature: [] };
  return (
    <>
      <UnstyledButton onClick={open} style={{ borderRadius: 8 }}>
        <Group gap={6} justify="center" c="dimmed">
          <IconCoin size={13} stroke={1.7} />
          <Text size="xs" ff="monospace">
            {data ? `${fmtTokens(total.total_tokens)} tok · $${total.total_usd.toFixed(4)}` : "—"}
          </Text>
        </Group>
      </UnstyledButton>
      <Modal opened={opened} onClose={close} title="Token 用量" centered>
        <Text size="sm" mb="sm">
          總計 {total.total_tokens.toLocaleString()} tokens · ${total.total_usd.toFixed(4)}
        </Text>
        <Table striped withTableBorder fz="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>功能</Table.Th><Table.Th>次數</Table.Th>
              <Table.Th>Tokens</Table.Th><Table.Th>USD</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {total.by_feature.map((f) => (
              <Table.Tr key={f.feature}>
                <Table.Td>{f.feature}</Table.Td>
                <Table.Td>{f.calls}</Table.Td>
                <Table.Td>{f.tokens.toLocaleString()}</Table.Td>
                <Table.Td>${f.usd.toFixed(4)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Button
          mt="md" color="red" variant="light" size="xs" fullWidth
          onClick={async () => {
            await resetUsage();
            qc.invalidateQueries({ queryKey: ["usage"] });
          }}
        >
          歸零
        </Button>
      </Modal>
    </>
  );
}
```

在底部 `Stack mt="auto"` 內、「上次」`Text` 之後加 `<UsageBadge />`：

```typescript
      <Stack mt="auto" gap={6}>
        <Button variant="subtle" color="gray" size="xs"
          leftSection={<IconSettings size={15} />} onClick={onOpenSettings}>
          設定
        </Button>
        <Button leftSection={<IconRefresh size={16} />}
          onClick={onRefresh} loading={running} disabled={running}>
          重新抓取
        </Button>
        <Text size="xs" c="dimmed" ta="center" ff="monospace">上次 {lastRun ?? "—"}</Text>
        <UsageBadge />
      </Stack>
```

- [ ] **Step 3: 前端建置驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: `✓ built`，零 TS 錯誤。（若 `@tanstack/react-query` 的 `QueryClientProvider` 尚未包住 app，確認 `main.tsx`/`App.tsx` 已有——SP 系列既有分頁都用 TanStack Query，理應已就緒；若無則報告，不自行大改架構。）

- [ ] **Step 4: 全後端測試回歸（確保無牽連）**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/Sidebar.tsx
git commit -m "feat(sentinel): 側欄左下角 token 用量/花費 badge + 明細 Modal（SP13）"
```

---

## 收尾（所有任務後）

- 最終全分支 review（opus）：重點驗 **記帳 best-effort 不影響 LLM 行為（零回歸）**、所有 LLM 出口都插樁、usage 正規化兩家 provider 正確、定價換算正確、前端 build 乾淨。
- 真機驗證（使用者）：跑健檢/比對/聊天 → 側欄左下角 token/USD 增加 → 點開看逐功能明細 → 歸零歸零。
- roadmap「隨手記/技術債」補一筆（**注意 Foundry 計費可能與 `_PRICING` 預設不同、可調**）。
- merge dev→main + push（自動部署——需明講）。
```