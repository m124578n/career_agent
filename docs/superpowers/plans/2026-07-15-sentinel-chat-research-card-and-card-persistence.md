# sentinel 聊天：查公司評價卡 + 確認卡持久化 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓聊天 agent 能提議「查公司評價」確認卡，並把聊天確認卡（含已生成結果）持久化，重載後卡片與結果都還在。

**Architecture:** 沿用既有 `<suggestions>` → 確認卡機制。後端在 `chat_send` 為每張卡指派 `card_id`、把 cards 存進 assistant `ChatMessage.suggestions`；run 卡結果由前端執行後 `POST /api/chat/card-result` 寫進 `ChatState.card_results`（card_id→result）。research 卡重用既有 `GET /api/research`。`suggestions`/`card_results` 純供 UI，永不進 LLM prompt。

**Tech Stack:** Python 3.12/uv、FastAPI、Pydantic v2、SQLite（`model_dump_json`/`model_validate_json` 存單列）、React+Vite+TS+Mantine。

## Global Constraints

- 後端測試：`./.venv/Scripts/python.exe -m pytest -q`（在 `sentinel/` 下）。前端驗收：`cd sentinel/web/frontend && npm run build`。
- **LLM 界線**：`build_messages` 只取每則訊息 `role`+`content`；`suggestions`/`card_results` **不得**進 prompt，不得序列化進 `content`。
- run 卡（tailor/negotiate/interview_prep/research）**不進** `suggestions.ALLOWED`、不走 `apply_update`。
- research 卡**重用** `GET /api/research?company=&force=`，**不新增** research 端點。
- 新增 Pydantic 欄位一律**帶預設值**（舊 DB 資料向後相容）。
- 繁體中文註解，密度與風格對齊周邊程式。
- `git add` 從 repo 根目錄用完整路徑（`sentinel/...`）。

---

### Task 1: 資料模型欄位 + 持久化 round-trip + LLM 界線

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`（`SuggestedUpdate`、`ChatMessage`、`ChatState`）
- Test: `sentinel/tests/test_chat_cards.py`（新）

**Interfaces:**
- Produces：
  - `SuggestedUpdate.card_id: str = ""`
  - `ChatMessage.suggestions: list[SuggestedUpdate] = []`
  - `ChatState.card_results: dict[str, dict] = {}`

- [ ] **Step 1: 寫失敗測試**（`sentinel/tests/test_chat_cards.py`）

```python
from career_sentinel import store
from career_sentinel.chat import prompt as chatprompt
from career_sentinel.models import ChatMessage, ChatState, SuggestedUpdate


def test_chat_state_roundtrip_keeps_suggestions_and_card_results(tmp_path):
    conn = store.connect(str(tmp_path / "db.sqlite"))
    st = ChatState(
        messages=[
            ChatMessage(role="user", content="這間華碩如何"),
            ChatMessage(role="assistant", content="我可以幫你查", suggestions=[
                SuggestedUpdate(field="research", op="run",
                                payload={"company": "華碩"}, card_id="cid1"),
            ]),
        ],
        card_results={"cid1": {"summary": "毀譽參半", "risk_level": "mid"}},
    )
    store.save_chat(conn, st)
    got = store.load_chat(conn)
    assert got.messages[1].suggestions[0].card_id == "cid1"
    assert got.messages[1].suggestions[0].field == "research"
    assert got.card_results["cid1"]["risk_level"] == "mid"


def test_build_messages_excludes_suggestions_and_card_results(tmp_path):
    st = ChatState(
        messages=[
            ChatMessage(role="assistant", content="我可以幫你查", suggestions=[
                SuggestedUpdate(field="research", op="run",
                                payload={"company": "華碩"}, card_id="cid1"),
            ]),
        ],
        card_results={"cid1": {"summary": "機密評價內容不該進 prompt"}},
    )
    msgs = chatprompt.build_messages(st, "下一步")
    blob = repr(msgs)
    assert "機密評價內容不該進 prompt" not in blob
    assert "cid1" not in blob
    assert "research" not in blob
    assert all(set(m.keys()) == {"role", "content"} for m in msgs)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_chat_cards.py -q`
Expected: FAIL（`SuggestedUpdate` 無 `card_id` / `ChatMessage` 無 `suggestions` / `ChatState` 無 `card_results`）

- [ ] **Step 3: 加欄位**（`models.py`）

`SuggestedUpdate` 加一欄（放在既有欄位後）：
```python
    card_id: str = ""  # 持久化確認卡的穩定鍵（live 與重載共用；對應 ChatState.card_results）
```
`ChatMessage` 改為：
```python
class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    suggestions: list["SuggestedUpdate"] = Field(default_factory=list)  # 該則附帶的確認卡（持久化）
```
`ChatState` 改為：
```python
class ChatState(BaseModel):
    summary: str = ""  # 更早對話的壓縮摘要
    messages: list[ChatMessage] = Field(default_factory=list)
    card_results: dict[str, dict] = Field(default_factory=dict)  # card_id -> run 卡生成結果
```
註：`SuggestedUpdate` 定義在 `ChatMessage` 之後，`ChatMessage.suggestions` 用字串前置參照 `"SuggestedUpdate"`；如既有順序已可直接參照則用實名。檔末若有 `model_rebuild()` 慣例則沿用；否則 Pydantic v2 會自動解析。

- [ ] **Step 4: 跑測試確認通過**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_chat_cards.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: 跑全套確認無回歸**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠（既有測試不受影響）

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/tests/test_chat_cards.py
git commit -m "feat(sentinel): ChatMessage.suggestions / ChatState.card_results 資料欄位"
```

---

### Task 2: chat_send 指派 card_id 並持久化 suggestions；chat_get 回 card_results

**Files:**
- Modify: `sentinel/src/career_sentinel/web/routers/chat.py`
- Test: `sentinel/tests/test_web_chat.py`（新增測試）

**Interfaces:**
- Consumes：Task 1 的 `ChatMessage.suggestions`、`ChatState.card_results`、`SuggestedUpdate.card_id`。
- Produces：`chat_send` 存的 assistant 訊息帶 `suggestions`（每張有 `card_id`）；`GET /api/chat` 回傳新增 `card_results`。

- [ ] **Step 1: 寫失敗測試**（加到 `tests/test_web_chat.py`）

```python
def test_chat_persists_cards_with_id(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    monkeypatch.setattr(llm, "chat_stream", _fake_stream([
        "幫你追蹤",
        '<suggestions>{"items":[{"field":"track","op":"set",'
        '"payload":{"code":"abc12","company":"台積電","title":"後端"}}]}</suggestions>',
    ]))
    c = _client(tmp_path)
    r = c.post("/api/chat", json={"message": "追蹤台積電後端"})
    assert r.status_code == 200
    # SSE 的 suggestions 帶 card_id
    sugg = dict(_events(r.text))["suggestions"]["items"]
    assert sugg[0]["card_id"]
    # 持久化：assistant 訊息帶 suggestions（含 card_id）
    st = store.load_chat(store.connect(tmp_path / "db.sqlite"))
    assert st.messages[-1].suggestions[0].field == "track"
    assert st.messages[-1].suggestions[0].card_id == sugg[0]["card_id"]


def test_chat_get_returns_card_results(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_chat(conn, ChatState(card_results={"cid1": {"summary": "x"}}))
    body = _client(tmp_path).get("/api/chat").json()
    assert body["card_results"]["cid1"]["summary"] == "x"
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_chat.py::test_chat_persists_cards_with_id tests/test_web_chat.py::test_chat_get_returns_card_results -q`
Expected: FAIL（suggestions 無 card_id / 未持久化 / chat_get 無 card_results）

- [ ] **Step 3: 改 `chat_send` 的 `gen()`**（`web/routers/chat.py`）

在 `import` 區加 `import uuid`（若尚無）。把
```python
        cards = [s for s in suggestions if s.field != "memory"]
```
之後、`if cards:` 送 SSE 之前，指派 card_id：
```python
        for c in cards:
            c.card_id = uuid.uuid4().hex
```
（因 SSE 用 `[c.model_dump() for c in cards]`，card_id 會一併送出。）
把持久化 assistant 訊息那行改為帶 suggestions：
```python
        st.messages.append(ChatMessage(role="assistant", content="".join(clean_parts), suggestions=cards))
```

- [ ] **Step 4: 改 `chat_get`**（同檔）

回傳字典加一鍵：
```python
    return {
        "summary": st.summary,
        "messages": [m.model_dump() for m in st.messages],
        "memory": [f.model_dump() for f in mem.facts],
        "card_results": st.card_results,
    }
```

- [ ] **Step 5: 跑測試確認通過 + 既有 chat 測試不回歸**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_chat.py -q`
Expected: PASS（含既有 `test_chat_streams_and_persists` 等；新加 card_id 不改變事件種類）

- [ ] **Step 6: Commit**

```bash
git add sentinel/src/career_sentinel/web/routers/chat.py sentinel/tests/test_web_chat.py
git commit -m "feat(sentinel): 聊天確認卡指派 card_id 並持久化；chat_get 回 card_results"
```

---

### Task 3: POST /api/chat/card-result 端點

**Files:**
- Modify: `sentinel/src/career_sentinel/web/routers/chat.py`
- Test: `sentinel/tests/test_web_chat.py`

**Interfaces:**
- Consumes：`ChatState.card_results`。
- Produces：`POST /api/chat/card-result`（body `{card_id: str, result: dict}`）寫入 `card_results`。

- [ ] **Step 1: 寫失敗測試**（加到 `tests/test_web_chat.py`）

```python
def test_card_result_persisted_and_returned(tmp_path):
    c = _client(tmp_path)
    r = c.post("/api/chat/card-result",
               json={"card_id": "cid1", "result": {"summary": "毀譽參半"}})
    assert r.status_code == 200 and r.json()["ok"] is True
    body = c.get("/api/chat").json()
    assert body["card_results"]["cid1"]["summary"] == "毀譽參半"


def test_card_result_rejects_empty_id_and_oversize(tmp_path):
    c = _client(tmp_path)
    assert c.post("/api/chat/card-result",
                  json={"card_id": "", "result": {"a": 1}}).status_code == 400
    big = {"x": "測" * 20001}
    assert c.post("/api/chat/card-result",
                  json={"card_id": "cid1", "result": big}).status_code == 400
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_chat.py::test_card_result_persisted_and_returned tests/test_web_chat.py::test_card_result_rejects_empty_id_and_oversize -q`
Expected: FAIL（端點 404）

- [ ] **Step 3: 加端點**（`web/routers/chat.py`，放在 `chat_get` 附近）

在 import 區確保有 `import json`（既有）。加請求模型與端點：
```python
class _CardResultReq(BaseModel):
    card_id: str
    result: dict


@router.post("/api/chat/card-result")
def chat_card_result(req: _CardResultReq, db_path: str = Depends(get_db_path)) -> dict:
    cid = req.card_id.strip()
    if not cid:
        raise HTTPException(status_code=400, detail="缺少 card_id")
    if len(json.dumps(req.result, ensure_ascii=False)) > 20000:
        raise HTTPException(status_code=400, detail="結果過大")
    conn = store.connect(db_path)
    st = store.load_chat(conn)
    st.card_results[cid] = req.result
    store.save_chat(conn, st)
    return {"ok": True}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_web_chat.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/web/routers/chat.py sentinel/tests/test_web_chat.py
git commit -m "feat(sentinel): POST /api/chat/card-result 持久化 run 卡結果"
```

---

### Task 4: maybe_compact 清 card_results 孤兒

**Files:**
- Modify: `sentinel/src/career_sentinel/chat/memory.py`
- Test: `sentinel/tests/test_chat_cards.py`

**Interfaces:**
- Consumes：`ChatState.card_results`、`ChatMessage.suggestions`。
- Produces：`maybe_compact` 產生的新 `ChatState.card_results` 只保留仍被保留訊息參照的 card_id。

- [ ] **Step 1: 寫失敗測試**（加到 `tests/test_chat_cards.py`）

```python
def test_maybe_compact_prunes_orphan_card_results(tmp_path, monkeypatch):
    from career_sentinel import llm
    from career_sentinel.chat import memory as chatmem
    conn = store.connect(str(tmp_path / "db.sqlite"))
    # 舊訊息帶 card old1、最近訊息帶 card keep1；訊息數需 > COMPACT_THRESHOLD(30)
    msgs = [ChatMessage(role="user", content=f"m{i}") for i in range(30)]
    msgs[0] = ChatMessage(role="assistant", content="舊", suggestions=[
        SuggestedUpdate(field="research", op="run", payload={"company": "A"}, card_id="old1")])
    msgs.append(ChatMessage(role="assistant", content="新", suggestions=[
        SuggestedUpdate(field="research", op="run", payload={"company": "B"}, card_id="keep1")]))
    st = ChatState(messages=msgs, card_results={"old1": {"s": 1}, "keep1": {"s": 2}})
    monkeypatch.setattr(llm, "chat_stream",
                        lambda messages, *, system=None, client=None, feature="": iter(["摘要"]))
    new = chatmem.maybe_compact(conn, st)
    assert "keep1" in new.card_results
    assert "old1" not in new.card_results  # 被壓掉的訊息其卡結果一併清除
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_chat_cards.py::test_maybe_compact_prunes_orphan_card_results -q`
Expected: FAIL（`old1` 仍留在 card_results）

- [ ] **Step 3: 改 `maybe_compact`**（`chat/memory.py`）

把
```python
    new_state = ChatState(summary=new_summary.strip(), messages=recent)
```
改為：
```python
    kept_ids = {s.card_id for m in recent for s in m.suggestions if s.card_id}
    kept_results = {k: v for k, v in state.card_results.items() if k in kept_ids}
    new_state = ChatState(summary=new_summary.strip(), messages=recent, card_results=kept_results)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_chat_cards.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/chat/memory.py sentinel/tests/test_chat_cards.py
git commit -m "feat(sentinel): compact 壓縮時清理孤兒 card_results"
```

---

### Task 5: prompt.py 加「查公司評價」提議 contract（Part A 後端）

**Files:**
- Modify: `sentinel/src/career_sentinel/chat/prompt.py`
- Test: `sentinel/tests/test_chat_apply.py`（新增 parse 測試）

**Interfaces:**
- Produces：agent 可輸出 `{"field":"research","op":"run","payload":{"company":"..."}}`；`parse_suggestions` 解析為 `SuggestedUpdate(field="research", op="run")`。

- [ ] **Step 1: 寫失敗測試**（加到 `tests/test_chat_apply.py`）

```python
def test_parse_suggestions_research():
    from career_sentinel.chat.suggestions import parse_suggestions
    tail = ('<suggestions>{"items":[{"field":"research","op":"run",'
            '"payload":{"company":"華碩"}}]}</suggestions>')
    got = parse_suggestions(tail)
    assert len(got) == 1
    assert got[0].field == "research" and got[0].op == "run"
    assert got[0].payload == {"company": "華碩"}


def test_system_prompt_mentions_research():
    from career_sentinel.chat.prompt import build_system_prompt
    from career_sentinel.models import (JobPreferences, MemoryState, ResumeState, Settings)
    sp = build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "research" in sp  # contract 有 research 提議型別
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py::test_parse_suggestions_research tests/test_chat_apply.py::test_system_prompt_mentions_research -q`
Expected: `test_parse_suggestions_research` 可能已 PASS（解析無白名單），`test_system_prompt_mentions_research` FAIL（prompt 未提 research）

- [ ] **Step 3: 改 `_CONTRACT`**（`chat/prompt.py`）

在 `<suggestions>` 範例陣列中（`interview_prep` 那筆後）加一行範例：
```
  {"field": "research", "op": "run", "payload": {"company": "華碩"}}
```
在規則區（`面試準備` 段之後）加一段：
```
- 查公司評價（research/run）：使用者想了解某公司風評／值不值得去／評價時，提議
  {"field": "research", "op": "run", "payload": {"company": "公司名"}}.
  company 取自對話或管道中的公司名、不得杜撰。這是**提議**，等使用者按下才實際上網查
  （花 LLM 錢＋web search）——**你不要自行編造公司評價或聲稱已查**，只丟提議卡。
```

- [ ] **Step 4: 跑測試確認通過 + 全套**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: 全綠

- [ ] **Step 5: Commit**

```bash
git add sentinel/src/career_sentinel/chat/prompt.py sentinel/tests/test_chat_apply.py
git commit -m "feat(sentinel): 聊天 agent 可提議『查公司評價』確認卡"
```

---

### Task 6: 前端 Part A — ResearchView 抽出 + ResearchCard + 接線

**Files:**
- Modify: `sentinel/web/frontend/src/ResearchButton.tsx`（抽出並匯出 `ResearchView`，自身改用）
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`（`ResearchCard` + render switch 分支）
- 驗收：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：既有 `getResearch(company, force)`、型別 `CompanyResearch`（`api.ts`，已存在）。
- Produces：`export function ResearchView({ data }: { data: CompanyResearch })`；`ChatPage` 對 `s.field === "research"` 渲染 `ResearchCard`。

- [ ] **Step 1: 抽出 `ResearchView`**（`ResearchButton.tsx`）

把 Modal 內「呈現結果」的 JSX（風險 badge / summary / 優缺點 Grid / 薪資 / 面試 / 來源 / 查於時間＋重新查詢）抽成同檔匯出元件：
```tsx
export function ResearchView({ data, onRefresh }: { data: CompanyResearch; onRefresh?: () => void }) {
  const risk = RISK[data.risk_level ?? "mid"] ?? RISK.mid;
  return ( /* 原 data && !busy 區塊的內容；「重新查詢」按鈕存在 onRefresh 時才顯示、呼叫 onRefresh */ );
}
```
`ResearchButton` 內 `{data && !busy && <ResearchView data={data} onRefresh={() => load(true)} />}`；`RISK` 常數移到可共用位置（同檔模組層即可）。行為與外觀不變。

- [ ] **Step 2: 加 `ResearchCard`**（`ChatPage.tsx`，照 `NegotiateCard`）

`import { getResearch, type CompanyResearch } from "./api";` 與 `import ResearchButton, { ResearchView } from "./ResearchButton";`（或依實際匯出調整）。
```tsx
function ResearchCard({ payload }: { payload: { company?: string } }) {
  const company = payload.company ?? "";
  const [result, setResult] = useState<CompanyResearch | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await getResearch(company);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "查詢失敗"); return; }
      setResult(b as CompanyResearch);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };
  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>查公司評價</b> {company}</Text>
        {!result && <Button size="compact-xs" loading={busy} onClick={run}>查評價</Button>}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && <ResearchView data={result} />}
    </Paper>
  );
}
```

- [ ] **Step 3: render switch 加分支**（`ChatPage.tsx` 卡片分派，`interview_prep` 之後、`SuggestionCard` 之前）

```tsx
: s.field === "research"
  ? <ResearchCard key={j} payload={(s.payload ?? {}) as { company?: string }} />
```

- [ ] **Step 4: build 驗收**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 建置成功、無型別錯誤

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/ResearchButton.tsx sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天 ResearchCard（查公司評價）＋共用 ResearchView"
```

---

### Task 7: 前端 Part B — 確認卡與結果持久化接線

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`（型別 + `saveCardResult`）
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`（載入映射 suggestions + card_results；run 卡接 cardId/initialResult 並回存）
- 驗收：`cd sentinel/web/frontend && npm run build`

**Interfaces:**
- Consumes：Task 2/3 的 `GET /api/chat` 回傳 `card_results`、`suggestions[].card_id`；`POST /api/chat/card-result`。
- Produces：重載後卡片與結果重現。

- [ ] **Step 1: `api.ts` 型別與函式**

- `SuggestedUpdate` 型別加 `card_id?: string;`
- `ChatMessage` 型別（回傳用）加 `suggestions?: SuggestedUpdate[];`
- `getChat` 回傳型別加 `card_results: Record<string, any>;`
- 新增：
```ts
export async function saveCardResult(cardId: string, result: unknown): Promise<Response> {
  return fetch("/api/chat/card-result", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ card_id: cardId, result }),
  });
}
```

- [ ] **Step 2: `ChatPage` 載入時映射 suggestions 與 card_results**

- 加狀態：`const [cardResults, setCardResults] = useState<Record<string, any>>({});`
- 載入處（現行 `setMsgs(history.data.messages.map((m) => ({ role: m.role, content: m.content })))`）改為：
```tsx
setMsgs(history.data.messages.map((m) => ({
  role: m.role, content: m.content, suggestions: m.suggestions,
})));
setCardResults(history.data.card_results ?? {});
```

- [ ] **Step 3: run 卡接 `cardId` 與 `initialResult` 並回存**

四張 run 卡（`TailorCard`/`NegotiateCard`/`InterviewPrepCard`/`ResearchCard`）改為接收 `cardId?: string` 與 `initialResult?: <對應型別>`：
- `const [result, setResult] = useState<T | null>(initialResult ?? null);`
- 執行成功、`setResult(b)` 後：`if (cardId) saveCardResult(cardId, b);`
- （`InterviewPrepCard`、`ResearchCard`、`TailorCard`、`NegotiateCard` 皆同一模式。）

render switch 對四張卡都多傳兩個 prop，例如：
```tsx
s.field === "tailor"
  ? <TailorCard key={j} cardId={s.card_id} initialResult={cardResults[s.card_id ?? ""]}
      payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
  : s.field === "negotiate"
    ? <NegotiateCard key={j} cardId={s.card_id} initialResult={cardResults[s.card_id ?? ""]}
        payload={...} />
    : s.field === "interview_prep"
      ? <InterviewPrepCard key={j} cardId={s.card_id} initialResult={cardResults[s.card_id ?? ""]}
          payload={...} />
      : s.field === "research"
        ? <ResearchCard key={j} cardId={s.card_id} initialResult={cardResults[s.card_id ?? ""]}
            payload={(s.payload ?? {}) as { company?: string }} />
        : <SuggestionCard key={j} s={s} />
```
（`TailorCard` 的 `runTailor` 已有 `trackJob`；保留，僅在 `setTailor(b)` 後另加 `if (cardId) saveCardResult(cardId, b);`。）

- [ ] **Step 4: build 驗收**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 建置成功、無型別錯誤

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天確認卡與生成結果重載後重現"
```

---

## 完成後

- 後端全套 `pytest -q` 全綠；前端 `npm run build` 通過。
- 重啟 `career-sentinel serve` 後手動驗收：聊天問「某公司如何」→ 出現查公司評價卡 → 按下查 → 重整頁面卡片與評價仍在；同理客製化/議價/面試準備。
