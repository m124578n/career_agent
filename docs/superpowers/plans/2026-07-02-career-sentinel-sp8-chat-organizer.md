# career-sentinel SP8 整理助手（對話式履歷/需求整理）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「整理助手」聊天分頁：SSE 串流聊天、LLM 回覆結尾帶 `<suggestions>` JSON 由後端截住解析成建議卡片一鍵套用、`op=remember` 自動寫入半永久 memory、對話超過門檻自動 compact。

**Architecture:** 單次 LLM 呼叫（方案 A）：`llm.chat_stream`（provider-aware 串流）→ `chat.py` 服務層（system prompt 組裝、`StreamFilter` 串流截斷狀態機、suggestions 解析、白名單套用、compact）→ `web/app.py` SSE 端點 → 前端 fetch ReadableStream 聊天分頁。三張新單列表（chat/preferences/memory）。

**Tech Stack:** Python 3.12、Pydantic v2、FastAPI StreamingResponse、httpx（OpenAI 相容 SSE）、anthropic SDK（Foundry stream）、React 18 + Mantine 7 + TanStack Query。

**Spec:** `docs/superpowers/specs/2026-07-02-career-sentinel-sp8-chat-organizer-design.md`

## Global Constraints

- SSE 事件序列固定：`delta`(多次) → `suggestions`(可省略) → `remembered`(可省略) → `done`；例外時發 `error` 後結束。
- 欄位白名單（`apply_update` 只認這些，其餘拒絕）：`target_title`/set、`expected_salary`/set、`locations`/set、`conditions`/set、`avoid`/set、`watched_companies`/set、`watched_keywords`/set、`resume_text`/replace_snippet+append_section、`memory`/remember。
- `op=remember` 自動寫入 memory、只走 `remembered` 事件、**不出現在** `suggestions.items`；其餘 op 一律等使用者按套用。
- `COMPACT_THRESHOLD = 30`、`COMPACT_KEEP = 10`（`chat.py` 模組常數）；compact **先成功寫入新 summary 才裁切 messages**，LLM 失敗整個跳過。
- 「清空對話」清 summary+messages、**memory 不清**。
- 串流中斷的回覆**不持久化**；持久化的訊息是「乾淨文字」（不含 `<suggestions>` 標記）。
- 無 LLM key：`POST /api/chat` 回 400（同 SP3 pattern）。
- 前端網路呼叫一律 try/finally 解鎖（SP-Search 教訓）。
- 測試不打真 LLM（fixture＋假 client/假串流）；測試輸出 pristine。
- 本地綁定 127.0.0.1 不變；PII 出口不新增類型（聊天送履歷＋偏好＋memory 給 LLM，與 SP3 同級）。
- 工作分支 `dev`；commit 訊息風格 `feat(sentinel): ...（SP8）`。

---

## File Structure

- Modify: `sentinel/src/career_sentinel/models.py` — 新 6 個 model（ChatMessage/ChatState/JobPreferences/MemoryFact/MemoryState/SuggestedUpdate）
- Modify: `sentinel/src/career_sentinel/store.py` — 3 張單列表 + `_load_single`/`_save_single` 共用 helper（既有 settings/resume 改走 helper）
- Modify: `sentinel/src/career_sentinel/llm.py` — `chat_stream`（openai SSE / foundry stream）
- Create: `sentinel/src/career_sentinel/chat.py` — 服務層（prompt、StreamFilter、parse_suggestions、apply_update、maybe_compact）
- Modify: `sentinel/src/career_sentinel/web/app.py` — 5 個端點
- Modify: `sentinel/web/frontend/src/api.ts` — 型別 + chat API + readSse
- Create: `sentinel/web/frontend/src/ChatPage.tsx` — 整理助手分頁
- Modify: `sentinel/web/frontend/src/App.tsx` — 第六個 Tab
- Test: `sentinel/tests/test_store.py`（追加）、`sentinel/tests/test_llm_stream.py`、`sentinel/tests/test_chat.py`、`sentinel/tests/test_chat_apply.py`、`sentinel/tests/test_web_chat.py`

所有後端指令都在 `sentinel/` 下執行（`cd sentinel`）。

---

### Task 1: 資料模型 + store 三張單列表

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（檔尾追加）
- Modify: `sentinel/src/career_sentinel/store.py`
- Test: `sentinel/tests/test_store.py`（檔尾追加）

**Interfaces:**
- Produces: `ChatMessage(role,content)`、`ChatState(summary:str="", messages:list[ChatMessage])`、`JobPreferences(locations/conditions/avoid: list[str])`、`MemoryFact(text, created_at:str="")`、`MemoryState(facts:list[MemoryFact])`、`SuggestedUpdate(field:str, op:str="set", value:str|int|list[str]|None=None, old:str|None=None, new:str|None=None)`；`store.load_chat/save_chat`、`store.load_preferences/save_preferences`、`store.load_memory/save_memory`（簽名同 `load_settings/save_settings`）。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_store.py` 檔尾追加）

```python
def test_chat_state_roundtrip(tmp_path):
    from career_sentinel.models import ChatMessage, ChatState
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_chat(conn) == ChatState()  # 空 DB 給預設
    st = ChatState(summary="聊過薪資", messages=[
        ChatMessage(role="user", content="期望薪資改 90 萬"),
        ChatMessage(role="assistant", content="好的"),
    ])
    store.save_chat(conn, st)
    assert store.load_chat(conn) == st


def test_preferences_roundtrip(tmp_path):
    from career_sentinel.models import JobPreferences
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_preferences(conn) == JobPreferences()
    prefs = JobPreferences(locations=["台北", "新北"], conditions=["可遠端"], avoid=["博弈"])
    store.save_preferences(conn, prefs)
    assert store.load_preferences(conn) == prefs


def test_memory_roundtrip(tmp_path):
    from career_sentinel.models import MemoryFact, MemoryState
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_memory(conn) == MemoryState()
    mem = MemoryState(facts=[MemoryFact(text="通勤以雙北為主", created_at="2026-07-02T10:00:00")])
    store.save_memory(conn, mem)
    assert store.load_memory(conn) == mem


def test_old_db_gains_new_tables(tmp_path):
    # 既有 DB（重連即跑 CREATE IF NOT EXISTS）也長得出新表 → 加法式遷移
    from career_sentinel.models import ChatState
    p = tmp_path / "db.sqlite"
    store.connect(p).close()
    conn = store.connect(p)
    assert store.load_chat(conn) == ChatState()
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_store.py -v -k "chat or preferences or memory or gains"`
Expected: FAIL（`AttributeError: module ... has no attribute 'load_chat'` 或 ImportError）

- [ ] **Step 3: 實作 models**（`sentinel/src/career_sentinel/models.py` 檔尾追加）

```python
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatState(BaseModel):
    summary: str = ""  # 更早對話的壓縮摘要
    messages: list[ChatMessage] = Field(default_factory=list)


class JobPreferences(BaseModel):
    locations: list[str] = Field(default_factory=list)   # 想要的工作地點
    conditions: list[str] = Field(default_factory=list)  # 軟條件
    avoid: list[str] = Field(default_factory=list)       # 避雷條件


class MemoryFact(BaseModel):
    text: str
    created_at: str = ""


class MemoryState(BaseModel):
    facts: list[MemoryFact] = Field(default_factory=list)


class SuggestedUpdate(BaseModel):
    field: str
    op: str = "set"  # set | replace_snippet | append_section | remember
    value: str | int | list[str] | None = None
    old: str | None = None  # replace_snippet 專用
    new: str | None = None  # replace_snippet 專用
```

- [ ] **Step 4: 實作 store**（`sentinel/src/career_sentinel/store.py`）

`_SCHEMA` 的 `resume` 表之後追加：

```sql
CREATE TABLE IF NOT EXISTS chat (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL
);
```

import 行改為：

```python
from .models import (
    Application, ChatState, Interview, JobPreferences, MemoryState,
    Message, ResumeState, Settings, Snapshot, Viewer,
)
```

檔尾加共用 helper，並把既有 4 個單列函式改為委派（行為不變，去重複）：

```python
def _load_single(conn: sqlite3.Connection, table: str, model_cls):
    row = conn.execute(f"SELECT data FROM {table} WHERE id = 1").fetchone()
    return model_cls.model_validate_json(row[0]) if row else model_cls()


def _save_single(conn: sqlite3.Connection, table: str, obj) -> None:
    conn.execute(
        f"INSERT OR REPLACE INTO {table} (id, data) VALUES (1, ?)",
        (obj.model_dump_json(),),
    )
    conn.commit()


def load_chat(conn: sqlite3.Connection) -> ChatState:
    return _load_single(conn, "chat", ChatState)


def save_chat(conn: sqlite3.Connection, state: ChatState) -> None:
    _save_single(conn, "chat", state)


def load_preferences(conn: sqlite3.Connection) -> JobPreferences:
    return _load_single(conn, "preferences", JobPreferences)


def save_preferences(conn: sqlite3.Connection, prefs: JobPreferences) -> None:
    _save_single(conn, "preferences", prefs)


def load_memory(conn: sqlite3.Connection) -> MemoryState:
    return _load_single(conn, "memory", MemoryState)


def save_memory(conn: sqlite3.Connection, mem: MemoryState) -> None:
    _save_single(conn, "memory", mem)
```

既有 `load_settings`/`save_settings`/`load_resume`/`save_resume` 改為：

```python
def load_settings(conn: sqlite3.Connection) -> Settings:
    return _load_single(conn, "settings", Settings)


def save_settings(conn: sqlite3.Connection, settings: Settings) -> None:
    _save_single(conn, "settings", settings)


def load_resume(conn: sqlite3.Connection) -> ResumeState:
    return _load_single(conn, "resume", ResumeState)


def save_resume(conn: sqlite3.Connection, state: ResumeState) -> None:
    _save_single(conn, "resume", state)
```

- [ ] **Step 5: 跑全套測試確認通過**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（既有 153 + 新 4；settings/resume 委派後既有測試不得變紅）

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/store.py sentinel/tests/test_store.py
git commit -m "feat(sentinel): SP8 資料模型 + chat/preferences/memory 單列表（store 抽 _load/_save_single）"
```

---

### Task 2: `llm.chat_stream`（provider-aware 串流）

**Files:**
- Modify: `sentinel/src/career_sentinel/llm.py`（檔尾追加）
- Test: `sentinel/tests/test_llm_stream.py`（新檔）

**Interfaces:**
- Consumes: `config.llm_provider() -> "openai"|"foundry"|""`、`llm_settings()`、`foundry_settings()`（已存在）。
- Produces: `llm.chat_stream(messages: list[dict], *, system: str | None = None, client=None) -> Iterator[str]`——多輪對話、yield 文字增量；無 key raise `RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")`。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_llm_stream.py` 新檔）

```python
import pytest

from career_sentinel import llm


class _FakeResp:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        pass

    def iter_lines(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeHttp:
    def __init__(self, lines):
        self._lines = lines
        self.captured = None

    def stream(self, method, url, **kw):
        self.captured = {"method": method, "url": url, **kw}
        return _FakeResp(self._lines)


def test_openai_chat_stream_yields_deltas(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
    fake = _FakeHttp([
        'data: {"choices":[{"delta":{"content":"你"}}]}',
        'data: {"choices":[{"delta":{"content":"好"}}]}',
        "data: {\"choices\":[]}",  # keepalive：空 choices 要略過
        "data: [DONE]",
    ])
    out = list(llm.chat_stream([{"role": "user", "content": "hi"}], system="s", client=fake))
    assert out == ["你", "好"]
    assert fake.captured["json"]["stream"] is True
    assert fake.captured["json"]["messages"][0] == {"role": "system", "content": "s"}


class _FakeAnthropicStream:
    def __init__(self, chunks):
        self.text_stream = iter(chunks)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeAnthropicMessages:
    def __init__(self, chunks):
        self._chunks = chunks
        self.captured = None

    def stream(self, **kw):
        self.captured = kw
        return _FakeAnthropicStream(self._chunks)


class _FakeAnthropic:
    def __init__(self, chunks):
        self.messages = _FakeAnthropicMessages(chunks)


def test_foundry_chat_stream_yields_deltas(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    fake = _FakeAnthropic(["嗨", "！"])
    out = list(llm.chat_stream([{"role": "user", "content": "hi"}], system="s", client=fake))
    assert out == ["嗨", "！"]
    assert fake.messages.captured["system"] == "s"
    assert fake.messages.captured["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_stream_no_key_raises(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        list(llm.chat_stream([{"role": "user", "content": "hi"}]))
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_llm_stream.py -v`
Expected: FAIL（`AttributeError: ... 'chat_stream'`）

- [ ] **Step 3: 實作**（`sentinel/src/career_sentinel/llm.py` 檔尾追加）

```python
def chat_stream(messages: list[dict], *, system: str | None = None, client=None):
    """多輪對話串流，yield 文字增量。依 provider 走 OpenAI 相容或 Foundry(Anthropic)。"""
    provider = llm_provider()
    if provider == "openai":
        yield from _openai_chat_stream(messages, system, client)
    elif provider == "foundry":
        yield from _foundry_chat_stream(messages, system, client)
    else:
        raise RuntimeError("請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")


def _openai_chat_stream(messages, system, client):
    cfg = llm_settings()
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    http = client or httpx.Client(timeout=300)
    owns_client = client is None
    try:
        with http.stream(
            "POST",
            f"{cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json={"model": cfg.model, "messages": msgs, "stream": True},
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                choices = json.loads(payload).get("choices") or []
                if not choices:
                    continue
                text = choices[0].get("delta", {}).get("content")
                if text:
                    yield text
    finally:
        if owns_client:
            http.close()


def _foundry_chat_stream(messages, system, client):
    fs = foundry_settings()
    if client is None:
        from anthropic import AnthropicFoundry

        client = AnthropicFoundry(api_key=fs.api_key, base_url=fs.base_url)
    kwargs: dict = {"model": fs.model, "max_tokens": 4096, "messages": messages}
    if system:
        kwargs["system"] = system
    with client.messages.stream(**kwargs) as stream:
        yield from stream.text_stream
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_llm_stream.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/llm.py sentinel/tests/test_llm_stream.py
git commit -m "feat(sentinel): llm.chat_stream 兩家 provider 串流（SP8）"
```

---

### Task 3: `chat.py` 服務層（prompt / StreamFilter / parse_suggestions）

**Files:**
- Create: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat.py`（新檔）

**Interfaces:**
- Consumes: Task 1 的 models；`llm._extract_json`（同 package 內部重用）。
- Produces: `SUGGESTIONS_OPEN = "<suggestions>"`、`SUGGESTIONS_CLOSE = "</suggestions>"`、`COMPACT_THRESHOLD = 30`、`COMPACT_KEEP = 10`；`build_system_prompt(resume: ResumeState, settings: Settings, prefs: JobPreferences, memory: MemoryState) -> str`；`build_messages(state: ChatState, user_msg: str) -> list[dict]`；`class StreamFilter`（`.feed(chunk:str)->str`、`.finish()->str`、`.tail()->str`）；`parse_suggestions(tail: str) -> list[SuggestedUpdate]`。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_chat.py` 新檔）

```python
from career_sentinel import chat
from career_sentinel.models import (
    ChatMessage, ChatState, JobPreferences, MemoryFact, MemoryState, ResumeState, Settings,
)


def test_system_prompt_embeds_state():
    p = chat.build_system_prompt(
        ResumeState(resume_text="Python 五年", target_title="後端工程師", expected_salary=900000),
        Settings(watched_companies=["台積電"], watched_keywords=["Python"]),
        JobPreferences(locations=["台北"], conditions=["可遠端"], avoid=["博弈"]),
        MemoryState(facts=[MemoryFact(text="通勤以雙北為主")]),
    )
    for needle in ("後端工程師", "900000", "台積電", "台北", "可遠端", "博弈",
                   "通勤以雙北為主", "Python 五年", "<suggestions>"):
        assert needle in p


def test_build_messages_with_summary_and_history():
    state = ChatState(summary="聊過薪資", messages=[
        ChatMessage(role="user", content="a"), ChatMessage(role="assistant", content="b"),
    ])
    msgs = chat.build_messages(state, "c")
    assert msgs[0]["role"] == "user" and "聊過薪資" in msgs[0]["content"]
    assert msgs[1]["role"] == "assistant"  # 摘要後補 assistant 回應，維持角色交替
    assert msgs[2:] == [
        {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]


def test_build_messages_no_summary():
    msgs = chat.build_messages(ChatState(), "hi")
    assert msgs == [{"role": "user", "content": "hi"}]


def test_stream_filter_plain_text_passthrough():
    f = chat.StreamFilter()
    out = f.feed("你好") + f.feed("！") + f.finish()
    assert out == "你好！"
    assert f.tail() == ""


def test_stream_filter_cuts_suggestions_block():
    f = chat.StreamFilter()
    out = f.feed("好的<suggestions>{\"items\":[]}") + f.feed("</suggestions>") + f.finish()
    assert out == "好的"
    assert f.tail() == "<suggestions>{\"items\":[]}</suggestions>"


def test_stream_filter_marker_split_across_chunks():
    f = chat.StreamFilter()
    out = f.feed("好的<sugg") + f.feed("estions>{}")
    out += f.finish()
    assert out == "好的"
    assert f.tail() == "<suggestions>{}"


def test_stream_filter_false_partial_marker_released_at_finish():
    f = chat.StreamFilter()
    out = f.feed("小於符號 <sugg")  # 不是標記、只是像
    out += f.finish()
    assert out == "小於符號 <sugg"


def test_parse_suggestions_valid():
    tail = '<suggestions>{"items":[{"field":"expected_salary","op":"set","value":900000}]}</suggestions>'
    items = chat.parse_suggestions(tail)
    assert len(items) == 1
    assert items[0].field == "expected_salary" and items[0].value == 900000


def test_parse_suggestions_bad_json_returns_empty():
    assert chat.parse_suggestions("<suggestions>{oops</suggestions>") == []
    assert chat.parse_suggestions("") == []
    assert chat.parse_suggestions("<suggestions>{\"items\": \"not-a-list\"}</suggestions>") == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_chat.py -v`
Expected: FAIL（ModuleNotFoundError: career_sentinel.chat）

- [ ] **Step 3: 實作**（`sentinel/src/career_sentinel/chat.py` 新檔）

```python
"""SP8 整理助手服務層：prompt 組裝、串流截斷、建議解析、套用、compact。"""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from . import llm, store
from .models import (
    ChatState, JobPreferences, MemoryFact, MemoryState, ResumeState, Settings, SuggestedUpdate,
)

SUGGESTIONS_OPEN = "<suggestions>"
SUGGESTIONS_CLOSE = "</suggestions>"
COMPACT_THRESHOLD = 30  # messages 超過此數觸發 compact
COMPACT_KEEP = 10       # compact 後保留的近期逐字訊息數
_RESUME_MAX_CHARS = 8000

_CONTRACT = """
當對話中出現應更新上述狀態的資訊時，在回覆文字結束後（最後）輸出一個建議區塊，格式：
<suggestions>{"items": [
  {"field": "expected_salary", "op": "set", "value": 900000},
  {"field": "locations", "op": "set", "value": ["台北", "新北"]},
  {"field": "resume_text", "op": "replace_snippet", "old": "原文片段", "new": "改後片段"},
  {"field": "resume_text", "op": "append_section", "value": "要附加的新段落"},
  {"field": "memory", "op": "remember", "value": "值得長期記住的使用者事實"}
]}</suggestions>
規則：
- 允許的 field/op：target_title/set、expected_salary/set（value 為整數年薪）、
  locations/set、conditions/set、avoid/set、watched_companies/set、watched_keywords/set
  （list 類 value 為完整字串列表，整列表取代）、
  resume_text/replace_snippet（old 必須逐字取自履歷全文）、resume_text/append_section、
  memory/remember（只記長期有效的偏好與事實，不記一次性資訊）。
- 沒有要更新時不要輸出 <suggestions> 區塊。
- <suggestions> 之後不要再有任何文字。
"""


def build_system_prompt(
    resume: ResumeState, settings: Settings, prefs: JobPreferences, memory: MemoryState,
) -> str:
    mem_lines = "\n".join(f"- {f.text}" for f in memory.facts) or "（無）"
    resume_text = resume.resume_text[:_RESUME_MAX_CHARS] or "（尚未上傳履歷）"
    head = (
        "你是「career-sentinel 整理助手」：用繁體中文陪使用者整理履歷與求職偏好。回覆口語、精簡。\n\n"
        "目前狀態：\n"
        f"- 目標職稱：{resume.target_title or '（未設定）'}\n"
        f"- 期望薪資：{resume.expected_salary or '（未設定）'}\n"
        f"- 求職偏好：地點={prefs.locations}；軟條件={prefs.conditions}；避雷={prefs.avoid}\n"
        f"- 關注公司：{settings.watched_companies}；關注關鍵字：{settings.watched_keywords}\n\n"
        f"長期記憶（半永久）：\n{mem_lines}\n\n"
        f"履歷全文（前 {_RESUME_MAX_CHARS} 字）：\n{resume_text}\n"
    )
    return head + _CONTRACT


def build_messages(state: ChatState, user_msg: str) -> list[dict]:
    msgs: list[dict] = []
    if state.summary:
        msgs.append({"role": "user", "content": "（先前對話摘要）" + state.summary})
        msgs.append({"role": "assistant", "content": "好的，我已掌握先前的討論脈絡。"})
    msgs.extend({"role": m.role, "content": m.content} for m in state.messages)
    msgs.append({"role": "user", "content": user_msg})
    return msgs


def _partial_marker_len(s: str) -> int:
    """s 尾端與 SUGGESTIONS_OPEN 開頭的最長重疊長度（處理標記跨 chunk）。"""
    for k in range(min(len(s), len(SUGGESTIONS_OPEN) - 1), 0, -1):
        if s.endswith(SUGGESTIONS_OPEN[:k]):
            return k
    return 0


class StreamFilter:
    """串流截斷狀態機：外流 <suggestions> 之前的文字，標記起全部截住供解析。"""

    def __init__(self) -> None:
        self._buf = ""
        self._capturing = False
        self._tail = ""

    def feed(self, chunk: str) -> str:
        if self._capturing:
            self._tail += chunk
            return ""
        self._buf += chunk
        idx = self._buf.find(SUGGESTIONS_OPEN)
        if idx != -1:
            out = self._buf[:idx]
            self._tail = self._buf[idx:]
            self._buf = ""
            self._capturing = True
            return out
        keep = _partial_marker_len(self._buf)
        out = self._buf[: len(self._buf) - keep]
        self._buf = self._buf[len(self._buf) - keep:]
        return out

    def finish(self) -> str:
        """串流結束：截留的尾端若不是標記，其實是一般文字，補吐出來。"""
        if self._capturing:
            return ""
        out = self._buf
        self._buf = ""
        return out

    def tail(self) -> str:
        return self._tail


def parse_suggestions(tail: str) -> list[SuggestedUpdate]:
    start = tail.find(SUGGESTIONS_OPEN)
    if start == -1:
        return []
    inner = tail[start + len(SUGGESTIONS_OPEN):]
    end = inner.find(SUGGESTIONS_CLOSE)
    if end != -1:
        inner = inner[:end]
    try:
        data = json.loads(llm._extract_json(inner))
        items = data.get("items")
        if not isinstance(items, list):
            return []
        return [SuggestedUpdate.model_validate(it) for it in items]
    except Exception:
        return []
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd sentinel && uv run pytest tests/test_chat.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat.py
git commit -m "feat(sentinel): chat 服務層——system prompt/StreamFilter/parse_suggestions（SP8）"
```

---

### Task 4: `chat.py` 套用白名單 + compact

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`（檔尾追加）
- Test: `sentinel/tests/test_chat_apply.py`（新檔）

**Interfaces:**
- Consumes: Task 1 的 store 函式、Task 2 的 `llm.chat_stream`、Task 3 的常數。
- Produces: `class ApplyResult(BaseModel)`（`ok: bool`、`message: str = ""`）；`apply_update(conn, upd: SuggestedUpdate) -> ApplyResult`；`maybe_compact(conn, state: ChatState) -> ChatState`；`ALLOWED: dict[str, set[str]]`。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_chat_apply.py` 新檔）

```python
from career_sentinel import chat, store
from career_sentinel.models import ChatMessage, ChatState, ResumeState, SuggestedUpdate


def _conn(tmp_path):
    return store.connect(tmp_path / "db.sqlite")


def test_apply_set_scalar_and_lists(tmp_path):
    conn = _conn(tmp_path)
    assert chat.apply_update(conn, SuggestedUpdate(field="target_title", op="set", value="後端工程師")).ok
    assert chat.apply_update(conn, SuggestedUpdate(field="expected_salary", op="set", value=900000)).ok
    assert chat.apply_update(conn, SuggestedUpdate(field="locations", op="set", value=["台北"])).ok
    assert chat.apply_update(conn, SuggestedUpdate(field="watched_companies", op="set", value=["台積電"])).ok
    assert store.load_resume(conn).target_title == "後端工程師"
    assert store.load_resume(conn).expected_salary == 900000
    assert store.load_preferences(conn).locations == ["台北"]
    assert store.load_settings(conn).watched_companies == ["台積電"]


def test_apply_salary_non_numeric_fails(tmp_path):
    r = chat.apply_update(_conn(tmp_path), SuggestedUpdate(field="expected_salary", op="set", value="九十萬"))
    assert not r.ok


def test_apply_whitelist_rejects(tmp_path):
    conn = _conn(tmp_path)
    assert not chat.apply_update(conn, SuggestedUpdate(field="resume_text", op="set", value="x")).ok
    assert not chat.apply_update(conn, SuggestedUpdate(field="diagnosis", op="set", value="x")).ok
    assert not chat.apply_update(conn, SuggestedUpdate(field="target_title", op="remember", value="x")).ok


def test_apply_replace_snippet(tmp_path):
    conn = _conn(tmp_path)
    store.save_resume(conn, ResumeState(resume_text="Python 三年經驗"))
    ok = chat.apply_update(conn, SuggestedUpdate(
        field="resume_text", op="replace_snippet", old="三年", new="五年"))
    assert ok.ok
    assert store.load_resume(conn).resume_text == "Python 五年經驗"
    miss = chat.apply_update(conn, SuggestedUpdate(
        field="resume_text", op="replace_snippet", old="不存在的片段", new="x"))
    assert not miss.ok and "手動" in miss.message


def test_apply_append_section(tmp_path):
    conn = _conn(tmp_path)
    store.save_resume(conn, ResumeState(resume_text="經歷 A"))
    assert chat.apply_update(conn, SuggestedUpdate(
        field="resume_text", op="append_section", value="技能：Bicep")).ok
    assert store.load_resume(conn).resume_text == "經歷 A\n\n技能：Bicep"


def test_apply_remember_appends_memory(tmp_path):
    conn = _conn(tmp_path)
    assert chat.apply_update(conn, SuggestedUpdate(field="memory", op="remember", value="不想進博弈業")).ok
    facts = store.load_memory(conn).facts
    assert len(facts) == 1 and facts[0].text == "不想進博弈業" and facts[0].created_at


def _mk_state(n: int) -> ChatState:
    return ChatState(messages=[
        ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"m{i}") for i in range(n)
    ])


def test_compact_below_threshold_noop(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    called = {"n": 0}
    monkeypatch.setattr(chat.llm, "chat_stream", lambda *a, **k: called.__setitem__("n", 1) or iter([]))
    state = _mk_state(30)
    assert chat.maybe_compact(conn, state) == state
    assert called["n"] == 0


def test_compact_over_threshold_summarizes_and_trims(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    monkeypatch.setattr(chat.llm, "chat_stream", lambda *a, **k: iter(["新", "摘要"]))
    state = _mk_state(31)
    store.save_chat(conn, state)
    out = chat.maybe_compact(conn, state)
    assert out.summary == "新摘要"
    assert len(out.messages) == chat.COMPACT_KEEP
    assert out.messages[-1].content == "m30"
    assert store.load_chat(conn) == out  # 已持久化


def test_compact_llm_failure_keeps_everything(tmp_path, monkeypatch):
    conn = _conn(tmp_path)
    def boom(*a, **k):
        raise RuntimeError("llm down")
    monkeypatch.setattr(chat.llm, "chat_stream", boom)
    state = _mk_state(31)
    store.save_chat(conn, state)
    out = chat.maybe_compact(conn, state)
    assert out == state  # 失敗跳過、不丟訊息
    assert store.load_chat(conn) == state
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_chat_apply.py -v`
Expected: FAIL（`AttributeError: ... 'apply_update'`）

- [ ] **Step 3: 實作**（`sentinel/src/career_sentinel/chat.py` 檔尾追加）

```python
ALLOWED: dict[str, set[str]] = {
    "target_title": {"set"},
    "expected_salary": {"set"},
    "locations": {"set"},
    "conditions": {"set"},
    "avoid": {"set"},
    "watched_companies": {"set"},
    "watched_keywords": {"set"},
    "resume_text": {"replace_snippet", "append_section"},
    "memory": {"remember"},
}


class ApplyResult(BaseModel):
    ok: bool
    message: str = ""


def _as_str_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if value is None or value == "":
        return []
    return [str(value)]


def apply_update(conn, upd: SuggestedUpdate) -> ApplyResult:
    ops = ALLOWED.get(upd.field)
    if ops is None or upd.op not in ops:
        return ApplyResult(ok=False, message=f"不允許的欄位或操作：{upd.field}/{upd.op}")
    if upd.field == "target_title":
        state = store.load_resume(conn)
        state.target_title = str(upd.value or "")
        store.save_resume(conn, state)
        return ApplyResult(ok=True)
    if upd.field == "expected_salary":
        state = store.load_resume(conn)
        try:
            state.expected_salary = int(upd.value) if upd.value not in (None, "") else None
        except (TypeError, ValueError):
            return ApplyResult(ok=False, message="期望薪資需為數字")
        store.save_resume(conn, state)
        return ApplyResult(ok=True)
    if upd.field in ("locations", "conditions", "avoid"):
        prefs = store.load_preferences(conn)
        setattr(prefs, upd.field, _as_str_list(upd.value))
        store.save_preferences(conn, prefs)
        return ApplyResult(ok=True)
    if upd.field in ("watched_companies", "watched_keywords"):
        settings = store.load_settings(conn)
        setattr(settings, upd.field, _as_str_list(upd.value))
        store.save_settings(conn, settings)
        return ApplyResult(ok=True)
    if upd.field == "resume_text":
        state = store.load_resume(conn)
        if upd.op == "append_section":
            state.resume_text = (state.resume_text.rstrip() + "\n\n" + str(upd.value or "")).strip()
        else:  # replace_snippet
            if not upd.old or upd.old not in state.resume_text:
                return ApplyResult(ok=False, message="找不到要替換的原文片段，請手動修改")
            state.resume_text = state.resume_text.replace(upd.old, upd.new or "", 1)
        store.save_resume(conn, state)
        return ApplyResult(ok=True)
    # memory / remember
    mem = store.load_memory(conn)
    mem.facts.append(MemoryFact(
        text=str(upd.value or ""),
        created_at=datetime.now().isoformat(timespec="seconds"),
    ))
    store.save_memory(conn, mem)
    return ApplyResult(ok=True)


def maybe_compact(conn, state: ChatState) -> ChatState:
    """messages 超過門檻時把舊訊息壓成 summary、留最近 COMPACT_KEEP 則。失敗整個跳過。"""
    if len(state.messages) <= COMPACT_THRESHOLD:
        return state
    old = state.messages[:-COMPACT_KEEP]
    recent = state.messages[-COMPACT_KEEP:]
    lines = "\n".join(f"{m.role}: {m.content}" for m in old)
    prompt = (
        ("先前摘要：\n" + state.summary + "\n\n" if state.summary else "")
        + "以下是求職整理對話的較舊片段，請壓縮成一段保留關鍵事實與決定的摘要（500 字內），"
        + "直接輸出摘要文字：\n" + lines
    )
    try:
        new_summary = "".join(llm.chat_stream([{"role": "user", "content": prompt}]))
    except Exception:
        return state  # 失敗跳過、下輪再試，永不丟逐字訊息
    if not new_summary.strip():
        return state
    new_state = ChatState(summary=new_summary.strip(), messages=recent)
    store.save_chat(conn, new_state)  # 先寫入新 summary+裁切後訊息（單一原子寫）
    return new_state
```

- [ ] **Step 4: 跑全套測試確認通過**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_apply.py
git commit -m "feat(sentinel): chat 套用白名單 + compact 機制（SP8）"
```

---

### Task 5: Web API（SSE 聊天 + 套用 + 歷史 + memory）

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_chat.py`（新檔）

**Interfaces:**
- Consumes: Task 3/4 的 `chat` 模組全部、`llm.chat_stream`、Task 1 的 store 函式。
- Produces: `POST /api/chat`（SSE）、`POST /api/chat/apply`、`GET /api/chat`、`DELETE /api/chat`、`DELETE /api/memory/{index}`——契約如 Global Constraints 與下方程式碼。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_web_chat.py` 新檔）

```python
import json

from fastapi.testclient import TestClient

from career_sentinel import llm, store
from career_sentinel.models import ChatMessage, ChatState, MemoryFact, MemoryState
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _fake_stream(chunks):
    def fake(messages, *, system=None, client=None):
        return iter(chunks)
    return fake


def test_chat_requires_llm_key(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    r = _client(tmp_path).post("/api/chat", json={"message": "hi"})
    assert r.status_code == 400


def test_chat_streams_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setattr(llm, "chat_stream", _fake_stream([
        "好的，", "已了解",
        '<suggestions>{"items":[{"field":"expected_salary","op":"set","value":900000},'
        '{"field":"memory","op":"remember","value":"不想進博弈業"}]}</suggestions>',
    ]))
    c = _client(tmp_path)
    r = c.post("/api/chat", json={"message": "薪資改90萬，我不想進博弈業"})
    assert r.status_code == 200
    evs = _events(r.text)
    kinds = [k for k, _ in evs]
    assert kinds == ["delta", "delta", "suggestions", "remembered", "done"]
    assert "".join(d["text"] for k, d in evs if k == "delta") == "好的，已了解"
    sugg = dict(evs)["suggestions"]["items"]
    assert len(sugg) == 1 and sugg[0]["field"] == "expected_salary"  # remember 不進卡片
    assert dict(evs)["remembered"]["facts"] == ["不想進博弈業"]
    # 持久化：乾淨訊息（無標記）＋memory 自動寫入
    conn = store.connect(tmp_path / "db.sqlite")
    st = store.load_chat(conn)
    assert [m.content for m in st.messages] == ["薪資改90萬，我不想進博弈業", "好的，已了解"]
    assert store.load_memory(conn).facts[0].text == "不想進博弈業"


def test_chat_error_event_and_no_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    def boom(messages, *, system=None, client=None):
        yield "半句"
        raise RuntimeError("connection reset")
    monkeypatch.setattr(llm, "chat_stream", boom)
    c = _client(tmp_path)
    evs = _events(c.post("/api/chat", json={"message": "hi"}).text)
    assert evs[0][0] == "delta" and evs[-1][0] == "error"
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_chat(conn).messages == []  # 中斷不持久化


def test_chat_apply_endpoint(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/chat/apply", json={"field": "target_title", "op": "set", "value": "後端"})
    assert r.status_code == 200 and r.json()["ok"] is True
    r2 = c.post("/api/chat/apply", json={"field": "diagnosis", "op": "set", "value": "x"})
    assert r2.status_code == 400
    r3 = c.post("/api/chat/apply", json={
        "field": "resume_text", "op": "replace_snippet", "old": "沒有這段", "new": "x"})
    assert r3.status_code == 200 and r3.json()["ok"] is False


def test_chat_get_and_clear_keeps_memory(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_chat(conn, ChatState(summary="s", messages=[ChatMessage(role="user", content="a")]))
    store.save_memory(conn, MemoryState(facts=[MemoryFact(text="f", created_at="t")]))
    c = _client(tmp_path)
    body = c.get("/api/chat").json()
    assert body["summary"] == "s" and body["messages"][0]["content"] == "a"
    assert body["memory"][0]["text"] == "f"
    assert c.delete("/api/chat").json() == {"ok": True}
    body2 = c.get("/api/chat").json()
    assert body2["messages"] == [] and body2["summary"] == ""
    assert body2["memory"][0]["text"] == "f"  # 清空對話不動 memory


def test_memory_delete(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_memory(conn, MemoryState(facts=[
        MemoryFact(text="f0", created_at="t"), MemoryFact(text="f1", created_at="t")]))
    c = _client(tmp_path)
    assert c.delete("/api/memory/0").json() == {"ok": True}
    assert [f["text"] for f in c.get("/api/chat").json()["memory"]] == ["f1"]
    assert c.delete("/api/memory/9").status_code == 404
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_chat.py -v`
Expected: FAIL（404 Not Found 之類）

- [ ] **Step 3: 實作端點**（`sentinel/src/career_sentinel/web/app.py`）

檔頭 import 修改：

```python
import json

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import calendar_link, chat as chatmod, config, diagnosis, diff, digest, jobfetch, llm, match, resume, store, watch
from ..models import ChatMessage, ChatState, ResumeState, Settings, SuggestedUpdate
from . import runner, scheduler
```

request model（`_MatchReq` 旁）：

```python
class _ChatReq(BaseModel):
    message: str
```

`create_app` 內、`/api/recommend` 之後追加（注意：SSE generator 在請求 handler 返回後、可能於不同執行緒執行，sqlite 連線須在 generator 內建立）：

```python
    @app.post("/api/chat")
    def chat_send(req: _ChatReq):
        if not config.llm_provider():
            raise HTTPException(status_code=400, detail="請先設定 LLM_API_KEY 或 FOUNDRY_API_KEY")
        conn = _conn()
        system = chatmod.build_system_prompt(
            store.load_resume(conn), store.load_settings(conn),
            store.load_preferences(conn), store.load_memory(conn),
        )
        messages = chatmod.build_messages(store.load_chat(conn), req.message)

        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        def gen():
            filt = chatmod.StreamFilter()
            clean_parts: list[str] = []
            try:
                for chunk in llm.chat_stream(messages, system=system):
                    out = filt.feed(chunk)
                    if out:
                        clean_parts.append(out)
                        yield _sse("delta", {"text": out})
                rest = filt.finish()
                if rest:
                    clean_parts.append(rest)
                    yield _sse("delta", {"text": rest})
            except Exception as exc:
                yield _sse("error", {"message": f"回覆中斷：{exc}"})
                return  # 中斷的回覆不持久化
            gconn = _conn()  # generator 可能跑在不同執行緒，sqlite 連線在此建立
            suggestions = chatmod.parse_suggestions(filt.tail())
            cards = [s for s in suggestions if s.op != "remember"]
            remembered = []
            for s in suggestions:
                if s.op == "remember" and chatmod.apply_update(gconn, s).ok:
                    remembered.append(str(s.value or ""))
            if cards:
                yield _sse("suggestions", {"items": [c.model_dump() for c in cards]})
            if remembered:
                yield _sse("remembered", {"facts": remembered})
            st = store.load_chat(gconn)
            st.messages.append(ChatMessage(role="user", content=req.message))
            st.messages.append(ChatMessage(role="assistant", content="".join(clean_parts)))
            store.save_chat(gconn, st)
            chatmod.maybe_compact(gconn, st)
            yield _sse("done", {})

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/chat/apply")
    def chat_apply(upd: SuggestedUpdate) -> dict:
        res = chatmod.apply_update(_conn(), upd)
        if not res.ok and res.message.startswith("不允許"):
            raise HTTPException(status_code=400, detail=res.message)
        return res.model_dump()

    @app.get("/api/chat")
    def chat_get() -> dict:
        conn2 = _conn()
        st = store.load_chat(conn2)
        mem = store.load_memory(conn2)
        return {
            "summary": st.summary,
            "messages": [m.model_dump() for m in st.messages],
            "memory": [f.model_dump() for f in mem.facts],
        }

    @app.delete("/api/chat")
    def chat_clear() -> dict:
        store.save_chat(_conn(), ChatState())
        return {"ok": True}

    @app.delete("/api/memory/{index}")
    def memory_delete(index: int) -> dict:
        conn2 = _conn()
        mem = store.load_memory(conn2)
        if not (0 <= index < len(mem.facts)):
            raise HTTPException(status_code=404, detail="memory 不存在")
        mem.facts.pop(index)
        store.save_memory(conn2, mem)
        return {"ok": True}
```

- [ ] **Step 4: 跑全套測試確認通過**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_chat.py
git commit -m "feat(sentinel): /api/chat SSE + apply/歷史/memory 端點（SP8）"
```

---

### Task 6: 前端「整理助手」分頁

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（檔尾追加）
- Create: `sentinel/web/frontend/src/ChatPage.tsx`
- Modify: `sentinel/web/frontend/src/App.tsx`

**Interfaces:**
- Consumes: Task 5 的 5 個端點（契約見 Global Constraints）。
- Produces: 使用者可見的第六個分頁「整理助手」。

- [ ] **Step 1: api.ts 追加**（`sentinel/web/frontend/src/api.ts` 檔尾）

```ts
export interface ChatMsg { role: string; content: string }
export interface SuggestedUpdate {
  field: string;
  op: string;
  value: string | number | string[] | null;
  old: string | null;
  new: string | null;
}
export interface MemoryFact { text: string; created_at: string }
export interface ChatHistory { summary: string; messages: ChatMsg[]; memory: MemoryFact[] }

export async function getChat(): Promise<ChatHistory> {
  const r = await fetch("/api/chat");
  return r.json();
}

export function sendChat(message: string): Promise<Response> {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function applyUpdate(u: SuggestedUpdate): Promise<Response> {
  return fetch("/api/chat/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(u),
  });
}

export async function clearChat(): Promise<void> {
  await fetch("/api/chat", { method: "DELETE" });
}

export async function deleteMemory(index: number): Promise<void> {
  await fetch(`/api/memory/${index}`, { method: "DELETE" });
}

// 解析 SSE 串流（event/data 區塊以空行分隔；處理跨 chunk 邊界）
export async function readSse(
  resp: Response,
  onEvent: (event: string, data: any) => void,
): Promise<void> {
  const reader = resp.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    for (;;) {
      const i = buf.indexOf("\n\n");
      if (i === -1) break;
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const ev = block.match(/^event: (.+)$/m);
      const data = block.match(/^data: (.+)$/m);
      if (ev && data) onEvent(ev[1], JSON.parse(data[1]));
    }
  }
}
```

- [ ] **Step 2: ChatPage**（`sentinel/web/frontend/src/ChatPage.tsx` 新檔）

```tsx
import {
  ActionIcon, Alert, Badge, Button, Card, Group, Loader, Paper, ScrollArea,
  Stack, Text, TextInput, Title,
} from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  applyUpdate, clearChat, deleteMemory, getChat, readSse, sendChat, SuggestedUpdate,
} from "./api";

interface UiMsg {
  role: string;
  content: string;
  suggestions?: SuggestedUpdate[];
  remembered?: string[];
  interrupted?: boolean;
}

const FIELD_LABEL: Record<string, string> = {
  target_title: "目標職稱", expected_salary: "期望薪資", locations: "地點",
  conditions: "軟條件", avoid: "避雷", watched_companies: "關注公司",
  watched_keywords: "關注關鍵字", resume_text: "履歷",
};

function fmtValue(v: string | number | string[] | null): string {
  if (Array.isArray(v)) return v.join("、");
  return String(v ?? "");
}

function SuggestionCard({ s }: { s: SuggestedUpdate }) {
  const qc = useQueryClient();
  const [state, setState] = useState<"idle" | "busy" | "ok" | "fail">("idle");
  const [msg, setMsg] = useState("");
  const label =
    s.op === "replace_snippet" ? `「${s.old}」→「${s.new}」`
    : s.op === "append_section" ? `附加：${fmtValue(s.value)}`
    : `→ ${fmtValue(s.value)}`;
  const apply = async () => {
    setState("busy");
    try {
      const r = await applyUpdate(s);
      const body = await r.json().catch(() => ({}));
      if (r.ok && body.ok) {
        setState("ok");
        qc.invalidateQueries({ queryKey: ["resume"] });
        qc.invalidateQueries({ queryKey: ["settings"] });
      } else {
        setState("fail");
        setMsg(body.message || body.detail || "無法套用");
      }
    } catch {
      setState("fail");
      setMsg("網路錯誤");
    }
  };
  return (
    <Card withBorder padding="xs" radius="md">
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm" style={{ wordBreak: "break-all" }}>
          <b>{FIELD_LABEL[s.field] ?? s.field}</b> {label}
        </Text>
        {state === "ok" ? (
          <Badge color="teal">已套用</Badge>
        ) : state === "fail" ? (
          <Badge color="red" title={msg}>無法套用</Badge>
        ) : (
          <Button size="compact-xs" loading={state === "busy"} onClick={apply}>
            套用
          </Button>
        )}
      </Group>
      {state === "fail" && msg && <Text size="xs" c="dimmed">{msg}</Text>}
    </Card>
  );
}

export default function ChatPage() {
  const qc = useQueryClient();
  const history = useQuery({ queryKey: ["chat"], queryFn: getChat });
  const [msgs, setMsgs] = useState<UiMsg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const viewport = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (history.data && !loaded) {
      setMsgs(history.data.messages.map((m) => ({ role: m.role, content: m.content })));
      setLoaded(true);
    }
  }, [history.data, loaded]);

  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight });
  }, [msgs]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    const patchLast = (fn: (m: UiMsg) => UiMsg) =>
      setMsgs((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
    try {
      const r = await sendChat(text);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        patchLast((m) => ({ ...m, content: body.detail || "傳送失敗", interrupted: true }));
        return;
      }
      await readSse(r, (event, data) => {
        if (event === "delta") patchLast((m) => ({ ...m, content: m.content + data.text }));
        if (event === "suggestions") patchLast((m) => ({ ...m, suggestions: data.items }));
        if (event === "remembered") {
          patchLast((m) => ({ ...m, remembered: data.facts }));
          qc.invalidateQueries({ queryKey: ["chat"] });
        }
        if (event === "error") patchLast((m) => ({ ...m, interrupted: true }));
      });
    } catch {
      patchLast((m) => ({ ...m, interrupted: true }));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!window.confirm("確定清空對話？（半永久記憶不會清除）")) return;
    await clearChat();
    setMsgs([]);
    qc.invalidateQueries({ queryKey: ["chat"] });
  };

  const removeFact = async (i: number) => {
    await deleteMemory(i);
    qc.invalidateQueries({ queryKey: ["chat"] });
  };

  return (
    <Group align="flex-start" p="md" gap="md" wrap="nowrap">
      <Stack style={{ flex: 1, minWidth: 0 }}>
        <Title order={4}>整理助手</Title>
        <Text size="sm" c="dimmed">
          邊聊邊整理履歷與求職偏好；助手的更新建議需按「套用」才會寫入。
        </Text>
        <ScrollArea h={480} viewportRef={viewport} type="auto">
          <Stack gap="sm" pr="sm">
            {msgs.map((m, i) => (
              <Stack key={i} gap={4} align={m.role === "user" ? "flex-end" : "flex-start"}>
                <Paper
                  withBorder
                  p="sm"
                  radius="md"
                  maw="85%"
                  bg={m.role === "user" ? "dark.5" : undefined}
                >
                  <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                    {m.content}
                    {busy && i === msgs.length - 1 && m.role === "assistant" && (
                      <Loader size="xs" ml={6} display="inline-block" />
                    )}
                  </Text>
                  {m.interrupted && (
                    <Text size="xs" c="red">回覆中斷</Text>
                  )}
                </Paper>
                {m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}
                {m.remembered?.map((f, j) => (
                  <Badge key={j} variant="light" color="grape">🧠 已記住：{f}</Badge>
                ))}
              </Stack>
            ))}
            {msgs.length === 0 && (
              <Alert color="gray" variant="light">
                跟我聊聊你的履歷或求職想法，例如「期望薪資改 90 萬」「我只想找雙北的工作」。
              </Alert>
            )}
          </Stack>
        </ScrollArea>
        <Group wrap="nowrap">
          <TextInput
            style={{ flex: 1 }}
            placeholder="輸入訊息，Enter 送出"
            value={input}
            onChange={(e) => setInput(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            disabled={busy}
          />
          <Button onClick={send} loading={busy}>送出</Button>
        </Group>
      </Stack>
      <Card withBorder w={280} style={{ flexShrink: 0 }}>
        <Group justify="space-between" mb="xs">
          <Title order={6}>🧠 半永久記憶</Title>
          <Button size="compact-xs" variant="subtle" color="red" onClick={clear}>
            清空對話
          </Button>
        </Group>
        <Stack gap={6}>
          {(history.data?.memory ?? []).map((f, i) => (
            <Group key={i} justify="space-between" wrap="nowrap" gap={4}>
              <Text size="xs" style={{ flex: 1 }}>{f.text}</Text>
              <ActionIcon size="xs" variant="subtle" color="red" onClick={() => removeFact(i)}>
                ✕
              </ActionIcon>
            </Group>
          ))}
          {(history.data?.memory ?? []).length === 0 && (
            <Text size="xs" c="dimmed">（尚無記憶——聊天中提到的長期偏好會自動記在這）</Text>
          )}
        </Stack>
      </Card>
    </Group>
  );
}
```

- [ ] **Step 3: App.tsx 加分頁**（`sentinel/web/frontend/src/App.tsx` 全檔改為）

```tsx
import { Tabs } from "@mantine/core";
import { useState } from "react";
import ChatPage from "./ChatPage";
import Dashboard from "./Dashboard";
import MatchPage from "./MatchPage";
import RecommendPage from "./RecommendPage";
import ResumePage from "./ResumePage";
import SearchPage from "./SearchPage";

export default function App() {
  const [tab, setTab] = useState<string | null>("dashboard");
  return (
    <Tabs value={tab} onChange={setTab} keepMounted={false} pt="sm">
      <Tabs.List px="md">
        <Tabs.Tab value="dashboard">儀表板</Tabs.Tab>
        <Tabs.Tab value="resume">履歷健檢</Tabs.Tab>
        <Tabs.Tab value="match">JD 比對</Tabs.Tab>
        <Tabs.Tab value="recommend">推薦</Tabs.Tab>
        <Tabs.Tab value="search">職缺搜尋</Tabs.Tab>
        <Tabs.Tab value="chat">整理助手</Tabs.Tab>
      </Tabs.List>
      <Tabs.Panel value="dashboard"><Dashboard onGoRecommend={() => setTab("recommend")} /></Tabs.Panel>
      <Tabs.Panel value="resume"><ResumePage /></Tabs.Panel>
      <Tabs.Panel value="match"><MatchPage /></Tabs.Panel>
      <Tabs.Panel value="recommend"><RecommendPage /></Tabs.Panel>
      <Tabs.Panel value="search"><SearchPage /></Tabs.Panel>
      <Tabs.Panel value="chat"><ChatPage /></Tabs.Panel>
    </Tabs>
  );
}
```

- [ ] **Step 4: 前端 build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: build 成功、無 TypeScript 錯誤

- [ ] **Step 5: 後端全套測試再跑一次**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/ChatPage.tsx sentinel/web/frontend/src/App.tsx
git commit -m "feat(sentinel): 前端整理助手分頁——串流聊天+建議卡片+memory 側欄（SP8）"
```

---

### Task 7: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`

- [ ] **Step 1: 真機驗證（需使用者操作）**

`cd sentinel && uv run career-sentinel serve` → 開「整理助手」分頁：
1. 說「期望薪資改 90 萬」→ 回覆串流顯示 → 出現建議卡片 → 按套用 → 履歷健檢分頁的期望薪資同步更新。
2. 說「我不想進博弈業」→ 出現「🧠 已記住」→ 側欄出現該筆 → 清空對話後側欄記憶仍在。
3. 說「履歷幫我補一段 Bicep 經驗」→ append_section 卡片 → 套用 → 履歷字數變多。
4. 重開 serve → 對話歷史仍在。

- [ ] **Step 2: roadmap 收尾**

`docs/superpowers/career-sentinel-roadmap.md`：SP8 表格列劃掉、✅ 區加 SP8 摘要（含測試數）、若有 review minors 記入技術債區、更新「最後更新」日期。

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/career-sentinel-roadmap.md
git commit -m "docs(sentinel): SP8 整理助手完成（roadmap 收尾）"
```
