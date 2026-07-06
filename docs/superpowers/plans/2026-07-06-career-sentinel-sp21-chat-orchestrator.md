# SP21：聊天當總指揮（第一階段）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在聊天系統提示注入整條管道脈絡、加 `get_pipeline` 讀取工具，並讓 agent 用既有 `<suggestions>` 確認卡提議「不花 LLM 錢」的管道動作（追蹤/設 offer/未錄取/重設/取消追蹤），由使用者一鍵確認後執行。

**Architecture:** 沿用既有兩個機制——Foundry 原生 tool use 迴圈（唯讀 `search_jobs`/`get_pipeline`，自動跑）與 `<suggestions>` 確認卡（`apply_update`，使用者確認才 mutation）。管道脈絡以純函式壓成摘要注入 system prompt；`SuggestedUpdate` 加 `payload` 承載結構化動作資料。

**Tech Stack:** Python 3.12 / Pydantic v2 / FastAPI / SQLite / anthropic(AnthropicFoundry) tool use；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- **mutation 只走確認卡**：track/job_offer/job_reject/job_reset/untrack 一律經 `<suggestions>` 卡 →`/api/chat/apply`→`apply_update`；**agent 絕不在工具迴圈裡執行 mutation**。工具迴圈只有唯讀 `search_jobs`/`get_pipeline`。
- **本階段不接 LLM 花錢動作**：比對/客製化/研究不進聊天（留 SP21b）。
- **管道脈絡 best-effort**：`format_pipeline_summary` 吃 `build_pipeline`（try/except→[]）；app.py 端再包 try，失敗則 `pipe_summary=""`，聊天不中斷。
- **memory 分支明確化**：`apply_update` 尾端 memory 邏輯改成明確 `if upd.field == "memory":`，新管道 field 不誤落 memory。
- **code 不杜撰**：提示合約要求 payload.code 必來自 `get_pipeline`/`search_jobs` 實際結果。
- **相容加法式**：`SuggestedUpdate.payload` 加法（舊 JSON 無此欄→None）；既有 field/op/卡片/memory 自動套用行為不變。
- **token 控制**：`format_pipeline_summary` 每組至多 `_PIPE_GROUP_LIMIT=5` 筆＋計數；`get_pipeline` 回精簡 JSON（不含 raw）。
- **PII/安全**：無新增外部呼叫（除既有 `search_jobs`）；`get_pipeline` 只讀本機 SQLite；不寫入 104；後端綁 `127.0.0.1`。
- 時間戳 `datetime.now().isoformat(timespec="seconds")`（store 既有）。
- **測試指令（後端）**：於 `sentinel/` 用 `./.venv/Scripts/python.exe -m pytest -q`（預設 shell python 缺 pytest，勿用）。
- **測試指令（前端）**：於 `sentinel/web/frontend/` 用 `npm run build`；刪除/新增後清乾淨殘留 import。

---

## File Structure

- `sentinel/src/career_sentinel/models.py` — `SuggestedUpdate` 加 `payload`。
- `sentinel/src/career_sentinel/chat.py` — `apply_update` 管道動作＋`ALLOWED`＋memory 明確化（T1）；`format_pipeline_summary`＋`build_system_prompt` 脈絡參數＋`_CONTRACT`＋工具說明（T2）；`get_pipeline` 工具＋`TOOL_LOOP_MAX`＋`_execute_tool`＋`_pipeline_tool_json`＋`stream_with_tools(db_path)`（T3）。
- `sentinel/src/career_sentinel/web/app.py` — 組 pipeline 摘要傳入 `build_system_prompt`；`_chat_events` 傳 `db_path`（T4）。
- `sentinel/web/frontend/src/api.ts` — `SuggestedUpdate` 加 `payload`（T5）。
- `sentinel/web/frontend/src/ChatPage.tsx` — 確認卡管道動作 label＋`FIELD_LABEL`＋成功後 invalidate snapshot（T5）。
- 測試：`test_chat_apply.py`（T1）、`test_chat_tools.py`（T2/T3）、`test_web_chat.py`（新，T4）。

---

### Task 1: `SuggestedUpdate.payload` ＋ apply_update 管道動作

**Files:**
- Modify: `sentinel/src/career_sentinel/models.py`
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_apply.py`

**Interfaces:**
- Produces:
  - `SuggestedUpdate.payload: dict | None = None`。
  - `chat.apply_update` 支援 field ∈ {track, job_offer, job_reject, job_reset, untrack}（op 皆 `set`），讀 `upd.payload`；缺 code → `ApplyResult(ok=False, message="缺少職缺代碼")`。
  - `chat.ALLOWED` 含上述五 field。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_chat_apply.py` 末尾加：

```python
def test_suggested_update_payload_roundtrip():
    u = SuggestedUpdate(field="job_offer", op="set", payload={"code": "x", "salary_year": 100})
    assert u.payload["code"] == "x"
    u2 = SuggestedUpdate(field="target_title", op="set", value="後端")
    assert u2.payload is None


def test_apply_track_adds_job(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={
        "code": "abc12", "company": "甲", "title": "後端",
        "url": "https://www.104.com.tw/job/abc12", "salary": "6萬"}))
    assert r.ok
    tj = store.get_tracked_job(conn, "abc12")
    assert tj is not None and tj.state == "interested" and tj.company == "甲" and tj.salary == "6萬"


def test_apply_job_offer_sets_state_and_detail(tmp_path):
    from career_sentinel.models import OfferDetail
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="job_offer", op="set", payload={
        "code": "of1", "salary_year": 1200000, "location": "台北", "level": "資深"}))
    assert r.ok
    tj = store.get_tracked_job(conn, "of1")
    assert tj.state == "offer"
    parsed = OfferDetail.model_validate_json(tj.offer_json)
    assert parsed.salary_year == 1200000 and parsed.location == "台北"


def test_apply_job_reject_and_reset(tmp_path):
    conn = _conn(tmp_path)
    chat.apply_update(conn, SuggestedUpdate(field="job_offer", op="set", payload={"code": "j1", "salary_year": 100}))
    assert chat.apply_update(conn, SuggestedUpdate(field="job_reject", op="set", payload={"code": "j1"})).ok
    assert store.get_tracked_job(conn, "j1").state == "rejected"
    assert store.get_tracked_job(conn, "j1").offer_json == ""
    assert chat.apply_update(conn, SuggestedUpdate(field="job_reset", op="set", payload={"code": "j1"})).ok
    assert store.get_tracked_job(conn, "j1").state == "interested"


def test_apply_untrack_removes(tmp_path):
    conn = _conn(tmp_path)
    chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={"code": "u1", "company": "甲"}))
    assert chat.apply_update(conn, SuggestedUpdate(field="untrack", op="set", payload={"code": "u1"})).ok
    assert store.get_tracked_job(conn, "u1") is None


def test_apply_pipeline_action_missing_code(tmp_path):
    conn = _conn(tmp_path)
    r = chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={"company": "甲"}))
    assert not r.ok and "代碼" in r.message


def test_apply_track_preserves_offer_terminal(tmp_path):
    # 對已 offer 職缺送 track（走 merge）→ 防降級：state 仍 offer、offer_json 保留（SP20 修正）
    from career_sentinel.models import OfferDetail
    conn = _conn(tmp_path)
    store.set_tracked_state(conn, "t1", "offer", offer=OfferDetail(salary_year=999))
    chat.apply_update(conn, SuggestedUpdate(field="track", op="set", payload={"code": "t1", "company": "甲"}))
    tj = store.get_tracked_job(conn, "t1")
    assert tj.state == "offer" and tj.offer_json != ""
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py -q`
Expected: FAIL（`payload` 欄不存在 / track 等 field 未允許）

- [ ] **Step 3: `SuggestedUpdate` 加 payload（`models.py`）**

`class SuggestedUpdate` 改為：

```python
class SuggestedUpdate(BaseModel):
    field: str
    op: str = "set"  # set | replace_snippet | append_section | remember
    value: str | int | list[str] | None = None
    old: str | None = None  # replace_snippet 專用
    new: str | None = None  # replace_snippet 專用
    payload: dict | None = None  # 管道動作的結構化資料（code + 動作參數）
```

- [ ] **Step 4: `ALLOWED` 加五個管道 field（`chat.py`）**

`ALLOWED` dict 末尾（`"memory": {"remember", "forget"},` 之後）加：

```python
    "track": {"set"},
    "job_offer": {"set"},
    "job_reject": {"set"},
    "job_reset": {"set"},
    "untrack": {"set"},
```

- [ ] **Step 5: apply_update 加管道分支 ＋ memory 明確化（`chat.py`）**

把 `apply_update` 從 `if upd.field == "resume_text":` 區塊**之後**到函式結尾（原本的 memory 無條件段）整段替換為：

```python
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
    if upd.field in ("track", "job_offer", "job_reject", "job_reset", "untrack"):
        payload = upd.payload or {}
        code = str(payload.get("code", "")).strip()
        if not code:
            return ApplyResult(ok=False, message="缺少職缺代碼")
        if upd.field == "track":
            store.merge_tracked_job(
                conn, code, state="interested",
                company=str(payload.get("company", "")), title=str(payload.get("title", "")),
                url=str(payload.get("url", "")), salary=str(payload.get("salary", "")),
            )
            return ApplyResult(ok=True)
        if upd.field == "job_offer":
            from .models import OfferDetail
            offer = OfferDetail(
                salary_year=payload.get("salary_year"), salary_month=payload.get("salary_month"),
                location=str(payload.get("location", "")), level=str(payload.get("level", "")),
                start_date=str(payload.get("start_date", "")), notes=str(payload.get("notes", "")),
            )
            store.set_tracked_state(conn, code, "offer", offer=offer)
            return ApplyResult(ok=True)
        if upd.field == "job_reject":
            store.set_tracked_state(conn, code, "rejected")
            return ApplyResult(ok=True)
        if upd.field == "job_reset":
            store.set_tracked_state(conn, code, "interested")
            return ApplyResult(ok=True)
        store.delete_tracked_job(conn, code)  # untrack
        return ApplyResult(ok=True)
    if upd.field == "memory":
        # memory / remember / forget（LLM 自動維護：重複不再記、過時的可刪）
        mem = store.load_memory(conn)
        text = str(upd.value or "").strip()
        if not text:
            return ApplyResult(ok=False, message="記憶內容為空")
        if upd.op == "forget":
            kept = [f for f in mem.facts if f.text.strip() != text]
            if len(kept) == len(mem.facts):
                return ApplyResult(ok=False, message="找不到要刪除的記憶")
            mem.facts = kept
            store.save_memory(conn, mem)
            return ApplyResult(ok=True)
        if any(f.text.strip() == text for f in mem.facts):
            return ApplyResult(ok=False, message="已有相同記憶，略過")
        mem.facts.append(MemoryFact(
            text=text,
            created_at=datetime.now().isoformat(timespec="seconds"),
        ))
        store.save_memory(conn, mem)
        return ApplyResult(ok=True)
    return ApplyResult(ok=False, message=f"不允許的欄位或操作：{upd.field}/{upd.op}")
```

（`store.merge_tracked_job`/`set_tracked_state`/`delete_tracked_job` 皆 SP15/SP20 既有函式；`OfferDetail` 就地 import 避免頂部循環顧慮。）

- [ ] **Step 6: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_apply.py -q`
Expected: PASS（含既有 memory/resume 測試）

- [ ] **Step 7: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/models.py sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_apply.py
git commit -m "feat(sentinel): SuggestedUpdate.payload + apply_update 管道動作（track/offer/reject/reset/untrack）（SP21）"
```

---

### Task 2: 管道脈絡摘要 ＋ system prompt ＋ 合約擴充

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Modify: `sentinel/tests/test_chat_tools.py`

**Interfaces:**
- Consumes: `PipelineJob`（models）、Task 1 的管道動作（合約要提及）。
- Produces:
  - `chat.format_pipeline_summary(jobs: list[PipelineJob]) -> str`（空清單→`""`；每組至多 `_PIPE_GROUP_LIMIT=5` 筆＋計數；含 code）。
  - `chat.build_system_prompt(resume, settings, prefs, memory, pipeline_summary: str = "") -> str`（多一參數，含「目前求職管道」段、工具說明含 get_pipeline、合約含管道動作）。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_chat_tools.py` 末尾加：

```python
def test_format_pipeline_summary_groups_and_counts():
    from career_sentinel.models import OfferDetail, PipelineJob
    jobs = [
        PipelineJob(key="a", code="a", company="甲", title="後端", state="offer",
                    offer=OfferDetail(salary_year=1200000)),
        PipelineJob(key="b", code="b", company="乙", title="前端", state="interviewing",
                    when="2026-07-10 14:00:00"),
        PipelineJob(key="c", code="c", company="丙", title="PM", state="interested"),
    ]
    s = chat.format_pipeline_summary(jobs)
    assert "offer" in s and "甲" in s and "1200000" in s
    assert "乙" in s and "2026-07-10" in s
    assert "（a）" in s  # code 供 agent 引用


def test_format_pipeline_summary_empty():
    assert chat.format_pipeline_summary([]) == ""


def test_format_pipeline_summary_group_limit():
    from career_sentinel.models import PipelineJob
    jobs = [PipelineJob(key=str(i), code=str(i), company=f"公司{i}", title="x", state="interested")
            for i in range(8)]
    s = chat.format_pipeline_summary(jobs)
    assert "8 筆" in s              # 計數顯示全部 8 筆
    assert "公司0" in s and "公司4" in s and "公司5" not in s  # 只列前 5 筆


def test_system_prompt_includes_pipeline_summary():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState(), "【管道摘要文字】")
    assert "目前求職管道" in p and "【管道摘要文字】" in p


def test_system_prompt_empty_pipeline_shows_placeholder():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState(), "")
    assert "管道目前無職缺" in p


def test_contract_mentions_pipeline_actions():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    for f in ("track", "job_offer", "job_reject", "job_reset", "untrack"):
        assert f in p
```

並把既有的 `test_system_prompt_mentions_tool_rules` 改為：

```python
def test_system_prompt_mentions_tool_rules():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "search_jobs" in p and "get_pipeline" in p
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: FAIL（`format_pipeline_summary` 不存在；build_system_prompt 無第 5 參數；prompt 無 get_pipeline）

- [ ] **Step 3: models import 補 `PipelineJob`（`chat.py`）**

把 `chat.py` 頂部 models import 改為含 `PipelineJob`：

```python
from .models import (
    ChatState, JobPreferences, MemoryFact, MemoryState, PipelineJob, ResumeState, Settings,
    SuggestedUpdate,
)
```

- [ ] **Step 4: 加 `format_pipeline_summary`（`chat.py`）**

在 `_RESUME_MAX_CHARS = 8000` 之後加常數，並在 `build_system_prompt` 之前加函式：

```python
_PIPE_GROUP_LIMIT = 5  # 每組摘要最多列幾筆
_PIPE_STATE_ORDER = ["interviewing", "offer", "applied", "tailored", "matched", "interested", "rejected"]
_PIPE_STATE_LABEL = {
    "interviewing": "面試中", "offer": "offer", "applied": "已投遞",
    "tailored": "已客製化", "matched": "已比對", "interested": "有興趣", "rejected": "未錄取",
}


def format_pipeline_summary(jobs: list[PipelineJob]) -> str:
    """把 build_pipeline 結果壓成給 system prompt 的精簡摘要（含 code 供引用）。空則回 ''。"""
    if not jobs:
        return ""
    groups: dict[str, list[PipelineJob]] = {}
    for j in jobs:
        groups.setdefault(j.state, []).append(j)
    lines: list[str] = []
    for state in _PIPE_STATE_ORDER:
        items = groups.get(state) or []
        if not items:
            continue
        lines.append(f"- {_PIPE_STATE_LABEL.get(state, state)}（{len(items)} 筆）：")
        for j in items[:_PIPE_GROUP_LIMIT]:
            extra = ""
            if state == "interviewing" and j.when:
                extra = f"，面試 {j.when}"
            elif state == "offer" and j.offer:
                if j.offer.salary_year is not None:
                    extra = f"，年薪 {j.offer.salary_year}"
                elif j.offer.salary_month is not None:
                    extra = f"，月薪 {j.offer.salary_month}"
            code = f"（{j.code}）" if j.code else ""
            lines.append(f"  · {j.company} · {j.title}{code}{extra}")
    return "\n".join(lines)
```

- [ ] **Step 5: `build_system_prompt` 加脈絡參數、改工具說明、改身分（`chat.py`）**

把 `build_system_prompt` 整個函式改為：

```python
def build_system_prompt(
    resume: ResumeState, settings: Settings, prefs: JobPreferences, memory: MemoryState,
    pipeline_summary: str = "",
) -> str:
    mem_lines = "\n".join(f"- {f.text}" for f in memory.facts) or "（無）"
    resume_text = resume.resume_text[:_RESUME_MAX_CHARS] or "（尚未上傳履歷）"
    head = (
        "你是「career-sentinel 求職總指揮」：用繁體中文陪使用者跑完整條求職流程"
        "（整理履歷與偏好、找職缺、追蹤管道、記錄 offer）。回覆口語、精簡。\n\n"
        "目前狀態：\n"
        f"- 目標職稱：{prefs.target_title or '（未設定）'}\n"
        f"- 期望月薪：{prefs.expected_salary or '（未設定）'}\n"
        f"- 求職偏好：地點={prefs.locations}；軟條件={prefs.conditions}；避雷={prefs.avoid}\n"
        f"- 關注公司：{settings.watched_companies}；關注關鍵字：{settings.watched_keywords}\n\n"
        f"長期記憶（半永久）：\n{mem_lines}\n\n"
        f"目前求職管道：\n{pipeline_summary or '（管道目前無職缺）'}\n\n"
        "工具：search_jobs 用關鍵字搜尋 104 職缺（使用者明確要找才用，關鍵字精簡 2–4 個詞）；"
        "get_pipeline 讀你目前的求職管道（要引用或操作既有職缺前，先用它確認 code 與現況）。工具呼叫請節制。\n\n"
        f"履歷全文（前 {_RESUME_MAX_CHARS} 字）：\n{resume_text}\n"
    )
    return head + _CONTRACT
```

- [ ] **Step 6: `_CONTRACT` 加管道動作範例與規則（`chat.py`）**

把 `_CONTRACT` 整個字串替換為：

```python
_CONTRACT = """
當對話中出現應更新上述狀態的資訊，或使用者要對職缺採取管道動作時，在回覆文字結束後（最後）輸出一個建議區塊，格式：
<suggestions>{"items": [
  {"field": "expected_salary", "op": "set", "value": 60000},
  {"field": "locations", "op": "set", "value": ["台北", "新北"]},
  {"field": "resume_text", "op": "replace_snippet", "old": "原文片段", "new": "改後片段"},
  {"field": "resume_text", "op": "append_section", "value": "要附加的新段落"},
  {"field": "memory", "op": "remember", "value": "值得長期記住的使用者事實"},
  {"field": "memory", "op": "forget", "value": "要刪除的既有記憶原文"},
  {"field": "track", "op": "set", "payload": {"code": "abc12", "company": "台積電", "title": "後端工程師", "url": "https://www.104.com.tw/job/abc12", "salary": "月薪6萬"}},
  {"field": "job_offer", "op": "set", "payload": {"code": "abc12", "salary_year": 1200000, "location": "台北", "level": "資深", "start_date": "2026-09-01", "notes": "含年終"}},
  {"field": "job_reject", "op": "set", "payload": {"code": "abc12", "company": "台積電"}},
  {"field": "job_reset", "op": "set", "payload": {"code": "abc12", "company": "台積電"}},
  {"field": "untrack", "op": "set", "payload": {"code": "abc12", "company": "台積電"}}
]}</suggestions>
規則：
- 允許的 field/op：target_title/set、expected_salary/set（value 為整數**月薪**；
  使用者若說年薪，先除以 12 四捨五入換算成月薪再填，並在回覆中說明換算結果）、
  locations/set、conditions/set、avoid/set、watched_companies/set、watched_keywords/set
  （list 類 value 為完整字串列表，整列表取代）、
  resume_text/replace_snippet（old 必須逐字取自履歷全文）、resume_text/append_section、
  memory/remember（只記長期有效的偏好與事實，不記一次性資訊；「長期記憶」清單已有的
  內容——包括同義改寫——不要重複 remember）、
  memory/forget（既有記憶過時或與新資訊矛盾時，主動輸出 forget 刪除舊記憶——value 需
  逐字等於清單中該條原文——並視需要接著 remember 更新後的內容，保持記憶清單精簡不重複）。
- 管道動作（track/job_offer/job_reject/job_reset/untrack）：一律用 payload 帶資料。
  track＝把職缺加入管道（追蹤）；job_offer＝標記錄取並記 offer 明細（payload 的 salary_year/
  salary_month 為整數，使用者說年薪填 salary_year、月薪填 salary_month）；job_reject＝標記未錄取；
  job_reset＝重設狀態；untrack＝取消追蹤。payload.code 必須來自 get_pipeline 或 search_jobs 的
  實際結果，**不得杜撰**。這些動作只是「提議」，會等使用者按下確認才生效——**不要在回覆中聲稱已完成**。
- 沒有要更新時不要輸出 <suggestions> 區塊。
- <suggestions> 之後不要再有任何文字。
"""
```

- [ ] **Step 7: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: PASS

- [ ] **Step 8: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): 管道脈絡注入 system prompt + get_pipeline 說明 + 合約含管道動作（SP21）"
```

---

### Task 3: `get_pipeline` 讀取工具 ＋ 多工具分派

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_tools.py`

**Interfaces:**
- Consumes: `pipeline.build_pipeline`、`store.connect`、Task 2 的常數。
- Produces:
  - `chat.TOOLS` 含 `get_pipeline`；`chat.TOOL_LOOP_MAX = 4`。
  - `chat._pipeline_tool_json(db_path: str | None) -> str`（唯讀 JSON；`None`/失敗→`"[]"`）。
  - `chat._execute_tool(name: str, tool_input: dict, db_path: str | None) -> tuple[dict | None, str, bool]`（event, result_text, is_error）。
  - `chat.stream_with_tools(messages, *, system, client=None, feature="整理助手", db_path=None)`。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_chat_tools.py` 末尾加：

```python
def test_pipeline_tool_json_no_db():
    assert chat._pipeline_tool_json(None) == "[]"


def test_pipeline_tool_json_reads_pipeline(tmp_path):
    from career_sentinel import store
    from career_sentinel.models import OfferDetail
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=1200000))
    data = json.loads(chat._pipeline_tool_json(db))
    row = next(j for j in data if j["code"] == "of1")
    assert row["state"] == "offer" and row["offer"]["salary_year"] == 1200000


def test_execute_tool_search_dispatch(monkeypatch):
    monkeypatch.setattr(chat, "_execute_search", lambda kw: (_jobs(1), "[]", False))
    event, text, is_error = chat._execute_tool("search_jobs", {"keyword": "python"}, None)
    assert event["type"] == "jobs" and event["keyword"] == "python" and len(event["items"]) == 1
    assert is_error is False


def test_execute_tool_get_pipeline_dispatch(tmp_path):
    from career_sentinel import store
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    event, text, is_error = chat._execute_tool("get_pipeline", {}, db)
    assert event is None and is_error is False and text == "[]"


def test_execute_tool_unknown():
    event, text, is_error = chat._execute_tool("nope", {}, None)
    assert event is None and is_error is True


def test_stream_with_tools_get_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    from career_sentinel import store
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    tu = _Blk("tool_use", id="p1", name="get_pipeline", input={})
    client = _FakeClient([
        ([], _FakeFinal("tool_use", [tu])),
        (["你目前沒有職缺"], _FakeFinal("end_turn", [_Blk("text", text="你目前沒有職缺")])),
    ])
    evs = list(chat.stream_with_tools(
        [{"role": "user", "content": "我的管道"}], system="s", client=client, db_path=db))
    assert [e["type"] for e in evs] == ["text"]  # get_pipeline 不 yield jobs 事件
    tr = client.messages.captured[1]["messages"][-1]["content"][0]
    assert tr["tool_use_id"] == "p1" and tr["content"] == "[]"
```

並把既有 `test_stream_with_tools_loop_limit` 改為以 `chat.TOOL_LOOP_MAX` 為準（因上限由 2 改 4）：

```python
def test_stream_with_tools_loop_limit(monkeypatch):
    monkeypatch.setenv("FOUNDRY_API_KEY", "k")
    monkeypatch.setattr(chat, "_execute_search", lambda kw: ([], "[]", False))
    n = chat.TOOL_LOOP_MAX
    def tu(i):
        return _Blk("tool_use", id=f"tu{i}", name="search_jobs", input={"keyword": f"k{i}"})
    turns = [([], _FakeFinal("tool_use", [tu(i)])) for i in range(n)]
    turns.append((["只好用現有結果回答"], _FakeFinal("end_turn", [_Blk("text", text="只好用現有結果回答")])))
    client = _FakeClient(turns)
    list(chat.stream_with_tools([{"role": "user", "content": "找"}], system="s", client=client))
    cap = client.messages.captured
    for i in range(n):
        assert "tools" in cap[i]
    assert "tools" not in cap[n]  # 達上限，最後一輪強制作答
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: FAIL（`_pipeline_tool_json`/`_execute_tool` 不存在；`stream_with_tools` 無 db_path；loop_limit 期望 4）

- [ ] **Step 3: import `pipeline`（`chat.py`）**

把 `from . import llm, store, usage` 改為：

```python
from . import llm, pipeline, store, usage
```

（`pipeline` 不 import chat，無循環。）

- [ ] **Step 4: `TOOL_LOOP_MAX` 2→4、`TOOLS` 加 get_pipeline（`chat.py`）**

`TOOL_LOOP_MAX = 2` 改為：

```python
TOOL_LOOP_MAX = 4       # 每輪對話最多執行幾次工具
```

`TOOLS` 改為：

```python
TOOLS = [
    {
        "name": "search_jobs",
        "description": "在 104 站內以關鍵字搜尋職缺。只在使用者明確要求找職缺時使用。",
        "input_schema": {
            "type": "object",
            "properties": {"keyword": {"type": "string", "description": "精簡的搜尋關鍵字"}},
            "required": ["keyword"],
        },
    },
    {
        "name": "get_pipeline",
        "description": "讀取使用者目前的求職管道（各狀態職缺、offer 明細、面試時間、job code）。要引用或操作既有職缺前先用它確認 code 與現況。",
        "input_schema": {"type": "object", "properties": {}},
    },
]
```

- [ ] **Step 5: 加 `_pipeline_tool_json` 與 `_execute_tool`（`chat.py`）**

在 `_execute_search` 之後加：

```python
def _pipeline_tool_json(db_path: str | None) -> str:
    """get_pipeline 執行體：開新連線讀管道，回精簡 JSON（唯讀 best-effort）。"""
    if not db_path:
        return "[]"
    try:
        conn = store.connect(db_path)
        jobs = pipeline.build_pipeline(conn)
    except Exception:
        return "[]"
    brief = [
        {"code": j.code, "company": j.company, "title": j.title, "state": j.state,
         "salary": j.salary, "match_score": j.match_score, "when": j.when,
         "offer": j.offer.model_dump() if j.offer else None}
        for j in jobs
    ]
    return json.dumps(brief, ensure_ascii=False)


def _execute_tool(name: str, tool_input: dict, db_path: str | None):
    """工具分派。回 (event_dict_or_None, result_text, is_error)。event 供 yield 給前端（如 jobs）。"""
    if name == "search_jobs":
        keyword = str((tool_input or {}).get("keyword", ""))
        jobs, result_text, is_error = _execute_search(keyword)
        event = None if is_error else {"type": "jobs", "keyword": keyword, "items": jobs}
        return event, result_text, is_error
    if name == "get_pipeline":
        return None, _pipeline_tool_json(db_path), False
    return None, f"未知工具：{name}", True
```

- [ ] **Step 6: `stream_with_tools` 加 db_path、改用 `_execute_tool`（`chat.py`）**

把 `stream_with_tools` 的簽章與工具執行段改為：

```python
def stream_with_tools(messages: list[dict], *, system: str, client=None, feature: str = "整理助手", db_path: str | None = None):
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
    # 結構性終止上限：即使 provider 在無 tools 輪仍回 tool_use 也不會無限迴圈
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
            event, result_text, is_error = _execute_tool(
                getattr(block, "name", ""), block.input or {}, db_path)
            tool_runs += 1
            if event is not None:
                yield event
            entry = {"type": "tool_result", "tool_use_id": block.id, "content": result_text}
            if is_error:
                entry["is_error"] = True
            results.append(entry)
        msgs = msgs + [
            {"role": "assistant", "content": final.content},
            {"role": "user", "content": results},
        ]
```

- [ ] **Step 7: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: PASS（含既有 happy_path / error_no_jobs_event，維持 search 行為）

- [ ] **Step 8: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): get_pipeline 讀取工具 + 多工具分派 + TOOL_LOOP_MAX 4（SP21）"
```

---

### Task 4: app.py 接線（管道摘要注入 ＋ db_path 傳遞）

**Files:**
- Modify: `sentinel/src/career_sentinel/web/app.py`
- Test: `sentinel/tests/test_web_chat.py`（新建）

**Interfaces:**
- Consumes: Task 2 `format_pipeline_summary`/`build_system_prompt(..., pipeline_summary)`；Task 3 `stream_with_tools(..., db_path=)`；`pipeline.build_pipeline`。
- Produces: `/api/chat` 的 system 含管道摘要、`_chat_events` 把 `resolved_db` 傳給 `stream_with_tools`。

- [ ] **Step 1: 寫失敗測試**

新建 `sentinel/tests/test_web_chat.py`：

```python
from fastapi.testclient import TestClient

from career_sentinel import chat as chatmod, config, store
from career_sentinel.models import OfferDetail
from career_sentinel.web import app as webapp


def test_chat_injects_pipeline_summary_and_db_path(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=1200000))

    monkeypatch.setattr(config, "llm_provider", lambda: "foundry")
    captured = {}

    def fake_stream(messages, *, system, db_path=None, **kw):
        captured["system"] = system
        captured["db_path"] = db_path
        yield {"type": "text", "text": "好"}

    monkeypatch.setattr(chatmod, "stream_with_tools", fake_stream)
    c = TestClient(webapp.create_app(db_path=db))
    r = c.post("/api/chat", json={"message": "我的管道現況"})
    assert r.status_code == 200
    assert "目前求職管道" in captured["system"]
    assert "of1" in captured["system"]         # 管道摘要含該職缺 code
    assert captured["db_path"] == db           # db_path 傳進工具迴圈


def test_chat_pipeline_summary_best_effort(tmp_path, monkeypatch):
    # build_pipeline 爆掉時 system 仍可組（pipe_summary=""），聊天不中斷
    db = str(tmp_path / "db.sqlite")
    store.connect(db)
    monkeypatch.setattr(config, "llm_provider", lambda: "foundry")
    monkeypatch.setattr(webapp.pipeline, "build_pipeline",
                        lambda conn: (_ for _ in ()).throw(RuntimeError("boom")))
    captured = {}

    def fake_stream(messages, *, system, db_path=None, **kw):
        captured["system"] = system
        yield {"type": "text", "text": "好"}

    monkeypatch.setattr(chatmod, "stream_with_tools", fake_stream)
    c = TestClient(webapp.create_app(db_path=db))
    r = c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert "管道目前無職缺" in captured["system"]  # 失敗退回佔位字
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_chat.py -q`
Expected: FAIL（system 未含管道摘要；`stream_with_tools` 未收到 db_path）

- [ ] **Step 3: `_chat_events` 加 db_path 傳遞（`app.py`）**

把模組層的 `_chat_events`（約 44 行）改為：

```python
def _chat_events(messages, system, db_path=None):
    """依 provider 產聊天事件流：foundry 走工具迴圈、openai 走既有純聊天。"""
    if config.llm_provider() == "foundry":
        yield from chatmod.stream_with_tools(messages, system=system, db_path=db_path)
    else:
        for chunk in llm.chat_stream(messages, system=system, feature="整理助手"):
            yield {"type": "text", "text": chunk}
```

- [ ] **Step 4: 組 pipeline 摘要傳入 build_system_prompt（`app.py`）**

把 `/api/chat` 內組 system 的段（約 345-349）改為：

```python
        conn = _conn()
        try:
            pipe_summary = chatmod.format_pipeline_summary(pipeline.build_pipeline(conn))
        except Exception:
            pipe_summary = ""
        system = chatmod.build_system_prompt(
            store.load_resume(conn), store.load_settings(conn),
            store.load_preferences(conn), store.load_memory(conn), pipe_summary,
        )
```

（`pipeline` 已在 app.py 第 14 行 import。）

- [ ] **Step 5: 呼叫 `_chat_events` 帶 db_path（`app.py`）**

把 `for ev in _chat_events(messages, system):`（約 360 行）改為：

```python
                for ev in _chat_events(messages, system, resolved_db):
```

（`resolved_db` 在 `create_app` 內、`gen()` 閉包可見。）

- [ ] **Step 6: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_web_chat.py -q`
Expected: PASS

- [ ] **Step 7: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 8: Commit**

```bash
git add sentinel/src/career_sentinel/web/app.py sentinel/tests/test_web_chat.py
git commit -m "feat(sentinel): /api/chat 注入管道摘要 + 傳 db_path 給工具迴圈（SP21）"
```

---

### Task 5: 前端 api.ts payload ＋ ChatPage 管道動作確認卡

**Files:**
- Modify: `sentinel/web/frontend/src/api.ts`
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`

**Interfaces:**
- Consumes: 後端 `/api/chat/apply` 已支援管道動作（Task 1）；`suggestions` 事件帶 `payload`（既有 SSE 骨架）。
- Produces: `SuggestedUpdate` 型別加 `payload`；確認卡能顯示並套用管道動作、成功後刷新 snapshot。

- [ ] **Step 1: api.ts `SuggestedUpdate` 加 payload**

把 `api.ts` 的 `SuggestedUpdate` interface（約 198 行）改為：

```ts
export interface SuggestedUpdate {
  field: string;
  op: string;
  value: string | number | string[] | null;
  old: string | null;
  new: string | null;
  payload?: Record<string, unknown> | null;
}
```

- [ ] **Step 2: ChatPage `FIELD_LABEL` 加管道動作（`ChatPage.tsx`）**

把 `FIELD_LABEL`（約 30 行）改為：

```tsx
const FIELD_LABEL: Record<string, string> = {
  target_title: "目標職稱", expected_salary: "期望薪資", locations: "地點",
  conditions: "軟條件", avoid: "避雷", watched_companies: "關注公司",
  watched_keywords: "關注關鍵字", resume_text: "履歷",
  track: "追蹤", job_offer: "標記錄取", job_reject: "標記未錄取",
  job_reset: "重設狀態", untrack: "取消追蹤",
};
```

- [ ] **Step 3: SuggestionCard 管道動作 label ＋ 成功刷新 snapshot（`ChatPage.tsx`）**

把 `SuggestionCard` 內的 `label` 計算（約 45-48 行）改為（在既有三種 op 之外，先判管道動作）：

```tsx
  const PIPE_FIELDS = ["track", "job_offer", "job_reject", "job_reset", "untrack"];
  const p = (s.payload ?? {}) as Record<string, any>;
  const pipeLabel =
    s.field === "track" ? `${p.company ?? ""} · ${p.title ?? ""}`
    : s.field === "job_offer"
      ? `${p.company ?? p.code ?? ""}${p.salary_year ? ` · 年薪 ${p.salary_year}` : p.salary_month ? ` · 月薪 ${p.salary_month}` : ""}`
    : `${p.company ?? p.code ?? ""}`;
  const label =
    PIPE_FIELDS.includes(s.field) ? pipeLabel
    : s.op === "replace_snippet" ? `「${s.old}」→「${s.new}」`
    : s.op === "append_section" ? `附加：${fmtValue(s.value)}`
    : `→ ${fmtValue(s.value)}`;
```

把 `apply` 成功分支（約 54-57 行）改為：

```tsx
      if (r.ok && body.ok) {
        setState("ok");
        qc.invalidateQueries({ queryKey: ["resume"] });
        qc.invalidateQueries({ queryKey: ["settings"] });
        if (PIPE_FIELDS.includes(s.field)) qc.invalidateQueries({ queryKey: ["snapshot"] });
      } else {
```

- [ ] **Step 4: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（`tsc -b && vite build` 無型別/未用 import 錯誤）

- [ ] **Step 5: Commit**

```bash
git add sentinel/web/frontend/src/api.ts sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天管道動作確認卡（追蹤/錄取/未錄取/重設/取消）+ payload（SP21）"
```

---

## Self-Review

**Spec coverage：**
- `SuggestedUpdate.payload` → T1 ✅
- apply_update 五管道動作 ＋ ALLOWED ＋ memory 明確化 → T1 ✅
- `format_pipeline_summary` ＋ system prompt 脈絡段 ＋ 工具說明含 get_pipeline ＋ 合約含管道動作 → T2 ✅
- `get_pipeline` 工具 ＋ `_execute_tool` 分派 ＋ `_pipeline_tool_json` ＋ `TOOL_LOOP_MAX` 4 ＋ `stream_with_tools(db_path)` → T3 ✅
- app.py 組管道摘要傳入 ＋ db_path 傳遞（best-effort）→ T4 ✅
- 前端 payload 型別 ＋ 確認卡管道 label ＋ 成功刷新 snapshot → T5 ✅
- Global Constraints（mutation 只走確認卡、best-effort、memory 明確化、token 控制、不接 LLM 花錢動作）各 Task 遵守 ✅

**Placeholder scan：** 無 TBD/TODO；每個改碼步驟含完整程式碼與確切指令。

**Type consistency：** `SuggestedUpdate.payload`（models/api.ts 一致）；管道 field 集合 {track, job_offer, job_reject, job_reset, untrack} 於 ALLOWED/apply_update/合約/前端 FIELD_LABEL/PIPE_FIELDS 一致；`format_pipeline_summary(jobs)->str`、`_execute_tool(name,input,db_path)->(event,text,is_error)`、`_pipeline_tool_json(db_path)->str`、`stream_with_tools(...,db_path=None)` 於 chat/app/測試一致；payload 欄位（code/company/title/url/salary；salary_year/salary_month/location/level/start_date/notes）與後端 merge_tracked_job/OfferDetail 一致。
