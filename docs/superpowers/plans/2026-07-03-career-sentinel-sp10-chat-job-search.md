# career-sentinel SP10 聊天中即時推職缺 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 整理助手聊天中，使用者明確要求找職缺時，LLM 以原生 Anthropic tool use 呼叫既有站內搜尋，職缺卡片（重用 JobRow）嵌入聊天訊息流、LLM 引用結果評論。

**Architecture:** `chat.stream_with_tools`（Foundry 工具迴圈、上限 2 次、達標最後一輪不帶 tools）→ 唯一工具 `search_jobs` 執行既有 `fetch_search`（tool_result 精簡 8 筆給 LLM；完整清單走新 SSE 事件 `jobs`）→ `/api/chat` 依 provider 分派（openai 照舊純聊天）→ 前端該則訊息內嵌 JobRow。`<suggestions>` 通道原封不動。

**Tech Stack:** Python 3.12、anthropic SDK（Foundry client tools + streaming）、FastAPI SSE、React 18 + Mantine 7。

**Spec:** `docs/superpowers/specs/2026-07-03-career-sentinel-sp10-chat-job-search-design.md`

## Global Constraints

- 工具只掛 **Foundry 路徑**；`openai` 路徑走既有 `llm.chat_stream` 純聊天（行為與 SP8 完全相同——既有測試不得變紅）。
- `TOOL_LOOP_MAX = 2`：第 3 次呼叫起不帶 `tools`（強制作答）；`JOBS_RESULT_LIMIT = 8`：tool_result 給 LLM 至多 8 筆精簡欄位（title/company/salary/url）。
- 搜尋失敗：`tool_result` 帶 `is_error: True` 與錯誤說明，**不發 jobs 事件**、串流不中斷。
- SSE 事件序：`delta*/jobs*` 交錯 → `suggestions?` → `remembered?` → `forgot?` → `done`；`jobs` payload＝`{keyword, items:[{code,url,title,company,salary,is_watched}]}`。
- system prompt 工具規則逐字：「只在使用者明確要求找職缺時使用 search_jobs；關鍵字精簡（2–4 個詞）；每輪對話至多 2 次。」
- `<suggestions>` 通道／StreamFilter／訊息持久化（乾淨文字）／compact／memory 全部不變；聊天職缺卡片**不持久化**。
- system 注入今天日期沿用 `llm._with_today`（`stream_with_tools` 內也要套）。
- 測試不打真 LLM／真 104（假 client＋monkeypatch）；輸出 pristine（僅既有 Starlette warning）。
- 前端：`npm run build` 零 TS 錯誤；Tabler icon 無 emoji；網路呼叫 try/finally。
- 分支 `dev`；commit `feat(sentinel): ...（SP10）`＋trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## File Structure

- Modify: `sentinel/src/career_sentinel/chat.py`（TOOLS/_execute_search/stream_with_tools＋system prompt 工具規則）
- Modify: `sentinel/src/career_sentinel/web/app.py`（`_chat_events` 分派＋jobs SSE）
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`（jobsBlocks＋JobRow 嵌入）
- Test: `sentinel/tests/test_chat_tools.py`（新）、`sentinel/tests/test_web_chat.py`（追加）

---

### Task 1: `chat.py` 工具迴圈（TOOLS / _execute_search / stream_with_tools）

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_tools.py`（新檔）

**Interfaces:**
- Consumes: `config.foundry_settings()`、`llm._with_today`、`scraper.search.fetch_search(kw) -> list[RecommendedJob]`（RecommendedJob 有 code/url/title/company/salary）。
- Produces: `TOOL_LOOP_MAX = 2`、`JOBS_RESULT_LIMIT = 8`、`TOOLS`（單一 search_jobs 定義）、`_execute_search(keyword) -> tuple[list, str, bool]`（jobs、tool_result 文字、is_error）、`stream_with_tools(messages: list[dict], *, system: str, client=None) -> Iterator[dict]`（yield `{"type":"text","text":str}` 與 `{"type":"jobs","keyword":str,"items":list[RecommendedJob]}`）。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_chat_tools.py` 新檔）

```python
import json

from career_sentinel import chat
from career_sentinel.models import RecommendedJob


class _Blk:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeFinal:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content


class _FakeStream:
    def __init__(self, texts, final):
        self.text_stream = iter(texts)
        self._final = final

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self._final


class _FakeMessages:
    def __init__(self, turns):
        self._turns = list(turns)  # [(texts, final), ...]
        self.captured = []

    def stream(self, **kw):
        self.captured.append(kw)
        texts, final = self._turns.pop(0)
        return _FakeStream(texts, final)


class _FakeClient:
    def __init__(self, turns):
        self.messages = _FakeMessages(turns)


def _jobs(n):
    return [RecommendedJob(code=f"c{i}", url=f"https://www.104.com.tw/job/c{i}",
                           title=f"職缺{i}", company=f"公司{i}", salary="月薪 5萬") for i in range(n)]


def test_stream_with_tools_happy_path(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setattr(chat, "_execute_search",
                        lambda kw: (_jobs(2), json.dumps([{"title": "職缺0"}]), False))
    tool_use = _Blk("tool_use", id="tu1", name="search_jobs", input={"keyword": "python 後端"})
    client = _FakeClient([
        (["我來搜尋"], _FakeFinal("tool_use", [_Blk("text", text="我來搜尋"), tool_use])),
        (["找到了，前兩筆不錯"], _FakeFinal("end_turn", [_Blk("text", text="找到了，前兩筆不錯")])),
    ])
    evs = list(chat.stream_with_tools(
        [{"role": "user", "content": "幫我找 python 後端"}], system="s", client=client))
    kinds = [e["type"] for e in evs]
    assert kinds == ["text", "jobs", "text"]
    assert evs[1]["keyword"] == "python 後端" and len(evs[1]["items"]) == 2
    # 第一輪帶 tools；第二輪 tool_runs=1 < 2 仍帶
    assert "tools" in client.messages.captured[0]
    assert "tools" in client.messages.captured[1]
    # 第二輪 messages 追加 assistant(content=final.content) + user(tool_result)
    msgs2 = client.messages.captured[1]["messages"]
    assert msgs2[-2]["role"] == "assistant"
    assert msgs2[-1]["role"] == "user"
    assert msgs2[-1]["content"][0]["type"] == "tool_result"
    assert msgs2[-1]["content"][0]["tool_use_id"] == "tu1"
    # system 有注入今天日期
    assert "今天日期：" in client.messages.captured[0]["system"]


def test_stream_with_tools_loop_limit(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setattr(chat, "_execute_search", lambda kw: ([], "[]", False))
    def tu(i):
        return _Blk("tool_use", id=f"tu{i}", name="search_jobs", input={"keyword": f"k{i}"})
    client = _FakeClient([
        ([], _FakeFinal("tool_use", [tu(1)])),
        ([], _FakeFinal("tool_use", [tu(2)])),
        (["只好用現有結果回答"], _FakeFinal("end_turn", [_Blk("text", text="只好用現有結果回答")])),
    ])
    list(chat.stream_with_tools([{"role": "user", "content": "找"}], system="s", client=client))
    cap = client.messages.captured
    assert "tools" in cap[0] and "tools" in cap[1]
    assert "tools" not in cap[2]  # 達上限，最後一輪強制作答


def test_stream_with_tools_error_no_jobs_event(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setattr(chat, "_execute_search", lambda kw: ([], "搜尋失敗：boom", True))
    tool_use = _Blk("tool_use", id="tu1", name="search_jobs", input={"keyword": "x"})
    client = _FakeClient([
        ([], _FakeFinal("tool_use", [tool_use])),
        (["抱歉搜尋失敗"], _FakeFinal("end_turn", [_Blk("text", text="抱歉搜尋失敗")])),
    ])
    evs = list(chat.stream_with_tools([{"role": "user", "content": "找"}], system="s", client=client))
    assert [e["type"] for e in evs] == ["text"]  # 無 jobs 事件
    tr = client.messages.captured[1]["messages"][-1]["content"][0]
    assert tr.get("is_error") is True


def test_execute_search_limits_and_error(monkeypatch):
    from career_sentinel.scraper import search as search_mod
    monkeypatch.setattr(search_mod, "fetch_search", lambda kw: _jobs(10))
    jobs, text, is_error = chat._execute_search("python")
    assert len(jobs) == 10 and is_error is False
    brief = json.loads(text)
    assert len(brief) == 8  # JOBS_RESULT_LIMIT
    assert set(brief[0].keys()) == {"title", "company", "salary", "url"}

    def boom(kw):
        raise RuntimeError("104 掛了")
    monkeypatch.setattr(search_mod, "fetch_search", boom)
    jobs2, text2, is_error2 = chat._execute_search("python")
    assert jobs2 == [] and is_error2 is True and "搜尋失敗" in text2


def test_system_prompt_mentions_tool_rules():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "search_jobs" in p and "至多 2 次" in p
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_chat_tools.py -q`
Expected: FAIL（AttributeError: chat has no stream_with_tools / TOOLS）

- [ ] **Step 3: 實作**（`sentinel/src/career_sentinel/chat.py`）

檔頭常數區（`CURATE_THRESHOLD` 之後）追加：

```python
TOOL_LOOP_MAX = 2       # 每輪對話最多執行幾次工具
JOBS_RESULT_LIMIT = 8   # tool_result 給 LLM 的精簡職缺數上限
```

`build_system_prompt` 的 `head` 內、`f"履歷全文（前 {_RESUME_MAX_CHARS} 字）：\n{resume_text}\n"` 之前插入一行：

```python
        "工具：你有 search_jobs 工具可搜尋 104 職缺。"
        "只在使用者明確要求找職缺時使用 search_jobs；關鍵字精簡（2–4 個詞）；每輪對話至多 2 次。\n\n"
```

檔尾追加：

```python
TOOLS = [{
    "name": "search_jobs",
    "description": "在 104 站內以關鍵字搜尋職缺。只在使用者明確要求找職缺時使用。",
    "input_schema": {
        "type": "object",
        "properties": {"keyword": {"type": "string", "description": "精簡的搜尋關鍵字"}},
        "required": ["keyword"],
    },
}]


def _execute_search(keyword: str):
    """執行站內搜尋工具。回 (jobs, tool_result文字, is_error)。"""
    from .scraper import search as search_mod

    try:
        jobs = search_mod.fetch_search(keyword.strip())
    except Exception as exc:
        return [], f"搜尋失敗：{exc}", True
    brief = [
        {"title": j.title, "company": j.company, "salary": j.salary, "url": j.url}
        for j in jobs[:JOBS_RESULT_LIMIT]
    ]
    return jobs, json.dumps(brief, ensure_ascii=False), False


def stream_with_tools(messages: list[dict], *, system: str, client=None):
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
    while True:
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

- [ ] **Step 4: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（211＋新 5）

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): chat 工具迴圈——search_jobs 原生 tool use（SP10）"
```

---

### Task 2: `/api/chat` provider 分派 + jobs SSE

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_chat.py`（檔尾追加）

**Interfaces:**
- Consumes: Task 1 的 `chatmod.stream_with_tools`；既有 `llm.chat_stream`、`watch.is_watched`。
- Produces: SSE 新事件 `jobs`（payload 見 Global Constraints）；openai 路徑行為不變。

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_web_chat.py` 檔尾追加）

```python
def test_chat_foundry_streams_jobs_events(tmp_path, monkeypatch):
    from career_sentinel import chat as chatmod
    from career_sentinel.models import RecommendedJob, Settings
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_settings(conn, Settings(watched_companies=["公司0"]))

    def fake_stream(messages, *, system):
        yield {"type": "text", "text": "我來搜尋"}
        yield {"type": "jobs", "keyword": "python 後端", "items": [
            RecommendedJob(code="c0", url="u0", title="職缺0", company="公司0", salary="月薪 5萬"),
            RecommendedJob(code="c1", url="u1", title="職缺1", company="公司1", salary="月薪 6萬"),
        ]}
        yield {"type": "text", "text": "找到了"}

    monkeypatch.setattr(chatmod, "stream_with_tools", fake_stream)
    c = _client(tmp_path)
    evs = _events(c.post("/api/chat", json={"message": "幫我找 python 後端"}).text)
    kinds = [k for k, _ in evs]
    assert kinds == ["delta", "jobs", "delta", "done"]
    jobs = dict(evs)["jobs"]
    assert jobs["keyword"] == "python 後端"
    assert jobs["items"][0]["is_watched"] is True   # 關注公司標記
    assert jobs["items"][1]["is_watched"] is False
    assert set(jobs["items"][0].keys()) == {"code", "url", "title", "company", "salary", "is_watched"}
    # 持久化的 assistant 訊息只含文字
    st = store.load_chat(store.connect(tmp_path / "db.sqlite"))
    assert st.messages[-1].content == "我來搜尋找到了"


def test_chat_openai_path_unchanged(tmp_path, monkeypatch):
    # openai 路徑仍走 llm.chat_stream（無工具），行為與 SP8 相同
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setattr(llm, "chat_stream", _fake_stream(["hi"]))
    evs = _events(_client(tmp_path).post("/api/chat", json={"message": "hi"}).text)
    assert [k for k, _ in evs] == ["delta", "done"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd sentinel && uv run pytest tests/test_web_chat.py -q -k "foundry or openai_path"`
Expected: `test_chat_foundry_streams_jobs_events` FAIL（無 jobs 事件）

- [ ] **Step 3: 實作**（`sentinel/src/career_sentinel/web/app.py`）

`chat_send` 內，`messages = chatmod.build_messages(store.load_chat(conn), req.message)` 之後加一行（settings 供 gen 內 is_watched 用——在 handler 執行緒先載）：

```python
        settings_snapshot = store.load_settings(conn)
```

module 層（`_snapshot_payload` 之前）加分派 helper：

```python
def _chat_events(messages, system):
    """依 provider 產聊天事件流：foundry 走工具迴圈、openai 走既有純聊天。"""
    if config.llm_provider() == "foundry":
        yield from chatmod.stream_with_tools(messages, system=system)
    else:
        for chunk in llm.chat_stream(messages, system=system):
            yield {"type": "text", "text": chunk}
```

gen() 的串流迴圈整段替換——原：

```python
            try:
                for chunk in llm.chat_stream(messages, system=system):
                    out = filt.feed(chunk)
                    if out:
                        clean_parts.append(out)
                        yield _sse("delta", {"text": out})
                rest = filt.finish()
```

改為：

```python
            try:
                for ev in _chat_events(messages, system):
                    if ev["type"] == "jobs":
                        yield _sse("jobs", {
                            "keyword": ev["keyword"],
                            "items": [
                                {
                                    "code": j.code, "url": j.url, "title": j.title,
                                    "company": j.company, "salary": j.salary,
                                    "is_watched": watch.is_watched(j.company, j.title, settings_snapshot),
                                }
                                for j in ev["items"]
                            ],
                        })
                        continue
                    out = filt.feed(ev["text"])
                    if out:
                        clean_parts.append(out)
                        yield _sse("delta", {"text": out})
                rest = filt.finish()
```

（`rest` 之後到 `done` 的既有程式碼完全不動。）

- [ ] **Step 4: 全套測試**

Run: `cd sentinel && uv run pytest -q`
Expected: 全綠（含既有 SP8 聊天測試——openai 路徑不變）

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_chat.py
git commit -m "feat(sentinel): /api/chat provider 分派 + jobs SSE 事件（SP10）"
```

---

### Task 3: 前端——聊天內職缺卡片

**Files:**
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`

**Interfaces:**
- Consumes: SSE `jobs` 事件；既有 `JobRow`（props `{job: RecommendedJob; canMatch: boolean}`）、`getResume`、`RecommendedJob` 型別（api.ts 已有，含 is_watched——不需改 api.ts）。

- [ ] **Step 1: imports 與型別**

`ChatPage.tsx` 檔頭：
- import 區加：`import JobRow from "./JobRow";`、Tabler import 加 `IconSearch`、api import 加 `getResume, type RecommendedJob`（併入既有的 `{ applyUpdate, clearChat, ... }` import）。
- `UiMsg` 介面加一行：

```tsx
  jobsBlocks?: { keyword: string; items: RecommendedJob[] }[];
```

- [ ] **Step 2: 事件處理**

元件內（`const history = useQuery(...)` 旁）加：

```tsx
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const canMatch = !!resume.data?.has_resume;
```

`readSse` 回呼中 `if (event === "delta") ...` 之後加一行（jobs 即到即掛、不等打字機 drain）：

```tsx
        if (event === "jobs") patchLast((m) => ({ ...m, jobsBlocks: [...(m.jobsBlocks ?? []), { keyword: data.keyword, items: data.items }] }));
```

- [ ] **Step 3: 渲染**

訊息渲染中 `{m.suggestions?.map(...)}` 那行**之前**插入：

```tsx
                {m.jobsBlocks?.map((b, j) => (
                  <Stack key={j} gap={6} w="100%" maw="92%">
                    <Group gap={6}>
                      <IconSearch size={13} style={{ color: "var(--mantine-color-dark-2)" }} />
                      <Text size="xs" c="dimmed">搜尋：{b.keyword}</Text>
                    </Group>
                    {b.items.length === 0 && <Text size="xs" c="dimmed">找不到符合的職缺</Text>}
                    {b.items.map((job) => <JobRow key={job.code} job={job} canMatch={canMatch} />)}
                  </Stack>
                ))}
```

- [ ] **Step 4: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 零 TS 錯誤

- [ ] **Step 5: Commit**

```bash
git add src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天內職缺卡片——jobs 事件+JobRow 嵌入（SP10）"
```

---

### Task 4: 真機驗證 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`

- [ ] **Step 1: 真機驗證（需使用者操作）**

serve 重啟 → Ctrl+F5 → 整理助手：
1. 說「幫我找 Python 後端的職缺」→ LLM 回覆中出現「搜尋：…」＋職缺卡片＋LLM 引用結果的評論
2. 卡片上「比對」「查評價 🔍」「去 104 看」可用
3. 一般整理對話（「期望薪資改 X」）**不觸發**搜尋、建議卡片照舊
4. 記憶/套用/匯出等 SP8 功能不受影響

- [ ] **Step 2: roadmap 收尾 + Commit**

SP10 表格列劃掉、✅ 區加摘要、review minors 記技術債區、更新日期。

```bash
git add docs/superpowers/career-sentinel-roadmap.md
git commit -m "docs(sentinel): SP10 聊天中推職缺完成（roadmap 收尾）"
```
