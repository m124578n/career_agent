# 聊天總指揮增能 A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 加 `get_job_detail` 唯讀工具、把搜尋結果移到右欄專門面板（只留最新一次）、給聊天視窗明確邊框並更新頁面標題為「求職總指揮」。

**Architecture:** 後端在既有 tool use 迴圈加一個唯讀工具 `get_job_detail`（curl 抓 104 JD，不需登入）。前端 ChatPage 把 `jobs` SSE 事件從訊息流內的 inline 渲染改成寫進單一 `search` state，渲染在加寬後的右欄專門面板；聊天訊息區包進帶邊框的容器。

**Tech Stack:** Python 3.12 / Pydantic v2 / curl_cffi / anthropic tool use；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- **唯讀、無 mutation**：`get_job_detail` 只讀（curl 公開抓取），不寫狀態、不寫 104、不需登入瀏覽器；與 search_jobs/get_pipeline 同屬工具迴圈自動跑的唯讀工具。
- **後端 SSE 契約不改**：`jobs` 事件 payload 不動；只改前端呈現位置（訊息流→右欄面板）。
- **只留最新一次搜尋**：`search` state 覆蓋式，不累積。
- **token 控制**：`get_job_detail` 的 description 截斷 `_JD_DESC_MAX=1500`；回精簡 JSON（不含 raw）。
- **相容**：`get_job_detail` 為加法工具；既有 search_jobs/get_pipeline 行為與既有 SSE 事件不變；移除 jobsBlocks 後既有 suggestions/remembered/forgot 卡片渲染不受影響。
- **測試指令（後端）**：於 `sentinel/` 用 `./.venv/Scripts/python.exe -m pytest -q`（預設 shell python 缺 pytest，勿用）。
- **測試指令（前端）**：於 `sentinel/web/frontend/` 用 `npm run build`；移除 jobsBlocks 後清乾淨殘留型別/import。

---

## File Structure

- `sentinel/src/career_sentinel/chat.py` — 加 `_JD_DESC_MAX`、`_execute_job_detail`、`TOOLS` 加 get_job_detail、`_execute_tool` 分派、build_system_prompt 工具說明（Task 1）。
- `sentinel/tests/test_chat_tools.py` — get_job_detail 測試（Task 1）。
- `sentinel/web/frontend/src/ChatPage.tsx` — 搜尋結果面板、右欄加寬、聊天視窗邊框、標題（Task 2）。

---

### Task 1: `get_job_detail` 唯讀工具（後端）

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_tools.py`

**Interfaces:**
- Consumes: `jobfetch.extract_job_code(url) -> str`（非 104 raise ValueError）、`jobfetch.fetch_job_detail(code, *, session=None) -> JobDetail`（curl；測試 mock）。
- Produces:
  - `chat._JD_DESC_MAX = 1500`。
  - `chat._execute_job_detail(code_or_url: str) -> tuple[None, str, bool]`（event 恆 None、result_text、is_error）。
  - `chat.TOOLS` 含 `get_job_detail`；`_execute_tool` 分派 get_job_detail。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_chat_tools.py` 末尾加：

```python
def test_execute_job_detail_by_code(monkeypatch):
    from career_sentinel import jobfetch
    from career_sentinel.models import JobDetail
    monkeypatch.setattr(jobfetch, "fetch_job_detail",
                        lambda code, **kw: JobDetail(title="後端工程師", company="甲", salary="月薪6萬",
                                                     location="台北", description="做後端"))
    event, text, is_error = chat._execute_job_detail("abc12")
    assert event is None and is_error is False
    data = json.loads(text)
    assert data["code"] == "abc12" and data["title"] == "後端工程師"
    assert data["company"] == "甲" and data["description"] == "做後端"


def test_execute_job_detail_truncates_description(monkeypatch):
    from career_sentinel import jobfetch
    from career_sentinel.models import JobDetail
    monkeypatch.setattr(jobfetch, "fetch_job_detail",
                        lambda code, **kw: JobDetail(title="t", description="x" * 5000))
    _, text, _ = chat._execute_job_detail("c1")
    assert len(json.loads(text)["description"]) == chat._JD_DESC_MAX


def test_execute_job_detail_by_url(monkeypatch):
    from career_sentinel import jobfetch
    from career_sentinel.models import JobDetail
    captured = {}
    def fake_fetch(code, **kw):
        captured["code"] = code
        return JobDetail(title="t")
    monkeypatch.setattr(jobfetch, "fetch_job_detail", fake_fetch)
    event, text, is_error = chat._execute_job_detail("https://www.104.com.tw/job/9zzz9")
    assert is_error is False and captured["code"] == "9zzz9"


def test_execute_job_detail_non_104_url_is_error():
    # 含 /job/ 進 url 分支，但非 104 → extract_job_code raise ValueError → is_error
    event, text, is_error = chat._execute_job_detail("https://www.linkedin.com/job/12345")
    assert event is None and is_error is True and "104" in text


def test_execute_job_detail_empty_is_error():
    event, text, is_error = chat._execute_job_detail("  ")
    assert is_error is True and "缺少" in text


def test_execute_job_detail_fetch_failure(monkeypatch):
    from career_sentinel import jobfetch
    def boom(code, **kw):
        raise RuntimeError("網路掛了")
    monkeypatch.setattr(jobfetch, "fetch_job_detail", boom)
    event, text, is_error = chat._execute_job_detail("c1")
    assert is_error is True and "失敗" in text


def test_execute_tool_get_job_detail_dispatch(monkeypatch):
    monkeypatch.setattr(chat, "_execute_job_detail", lambda x: (None, '{"ok":1}', False))
    event, text, is_error = chat._execute_tool("get_job_detail", {"code_or_url": "abc12"}, None)
    assert event is None and text == '{"ok":1}' and is_error is False


def test_system_prompt_mentions_get_job_detail():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "get_job_detail" in p
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: FAIL（`_execute_job_detail`/`_JD_DESC_MAX` 不存在；prompt 無 get_job_detail）

- [ ] **Step 3: 加 `_JD_DESC_MAX` 與 `_execute_job_detail`（`chat.py`）**

在 `_execute_search` 之後（或 `_pipeline_tool_json` 附近）加：

```python
_JD_DESC_MAX = 1500  # JD description 截斷（控 token）


def _execute_job_detail(code_or_url: str):
    """get_job_detail 執行體。回 (None, result_text, is_error)。唯讀、需真網路。"""
    from . import jobfetch

    raw = (code_or_url or "").strip()
    if not raw:
        return None, "缺少職缺代碼或網址", True
    if "/job/" in raw or "104.com.tw" in raw:
        try:
            code = jobfetch.extract_job_code(raw)
        except ValueError:
            return None, "無法從網址取得 104 職缺代碼（請確認是 104 職缺網址）", True
    else:
        code = raw
    try:
        jd = jobfetch.fetch_job_detail(code)
    except Exception:
        return None, "抓取職缺詳情失敗，請確認代碼或稍後再試", True
    brief = {
        "code": code, "title": jd.title, "company": jd.company, "salary": jd.salary,
        "location": jd.location, "work_exp": jd.work_exp, "education": jd.education,
        "majors": jd.majors, "specialties": jd.specialties,
        "description": (jd.description or "")[:_JD_DESC_MAX],
    }
    return None, json.dumps(brief, ensure_ascii=False), False
```

- [ ] **Step 4: `TOOLS` 加 get_job_detail（`chat.py`）**

`TOOLS` list 末尾（get_pipeline 之後）加一項：

```python
    {
        "name": "get_job_detail",
        "description": "抓取指定 104 職缺的完整 JD（職務內容、需求條件、薪資、地點）。可傳 job code 或 104 職缺網址。回答職缺問題、比較職缺、給客製化建議前用它讀 JD。",
        "input_schema": {
            "type": "object",
            "properties": {"code_or_url": {"type": "string", "description": "104 job code 或職缺網址"}},
            "required": ["code_or_url"],
        },
    },
```

- [ ] **Step 5: `_execute_tool` 加分派（`chat.py`）**

在 `_execute_tool` 的 get_pipeline 分支之後、未知工具 return 之前加：

```python
    if name == "get_job_detail":
        return _execute_job_detail(str((tool_input or {}).get("code_or_url", "")))
```

- [ ] **Step 6: build_system_prompt 工具說明加 get_job_detail（`chat.py`）**

把 `build_system_prompt` head 的工具說明段改為（在 get_pipeline 之後加一句）：

```python
        "工具：search_jobs 用關鍵字搜尋 104 職缺（使用者明確要找才用，關鍵字精簡 2–4 個詞）；"
        "get_pipeline 讀你目前的求職管道（要引用或操作既有職缺前，先用它確認 code 與現況）；"
        "get_job_detail 讀指定職缺的完整 JD（傳 code 或網址；回答職缺細節、比較、給建議前先讀）。工具呼叫請節制。\n\n"
```

- [ ] **Step 7: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: PASS（含既有 search/get_pipeline/prompt 測試）

- [ ] **Step 8: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): get_job_detail 唯讀工具（聊天抓指定職缺 JD）"
```

---

### Task 2: 搜尋結果側邊面板 ＋ 聊天視窗邊框 ＋ 標題（前端）

**Files:**
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`

**Interfaces:**
- Consumes: 既有 `jobs` SSE 事件 `{keyword, items:[RecommendedJob]}`；`JobRow`、`RecommendedJob`、`trackedCodes`、`canMatch`。

- [ ] **Step 1: `UiMsg` 移除 `jobsBlocks`（`ChatPage.tsx`）**

把 `interface UiMsg` 的 `jobsBlocks?: ...` 那行刪除：

```tsx
interface UiMsg {
  role: string;
  content: string;
  suggestions?: SuggestedUpdate[];
  remembered?: string[];
  forgot?: string[];
  interrupted?: boolean;
}
```

- [ ] **Step 2: 加 `search` state（`ChatPage.tsx`）**

在既有 state 宣告區（`const [input, setInput] = useState("");` 附近）加：

```tsx
  const [search, setSearch] = useState<{ keyword: string; items: RecommendedJob[] } | null>(null);
```

- [ ] **Step 3: `jobs` 事件改寫 search state（`ChatPage.tsx`）**

把 SSE 迴圈裡的 jobs 那行（約 169）：

```tsx
        if (event === "jobs") patchLast((m) => ({ ...m, jobsBlocks: [...(m.jobsBlocks ?? []), { keyword: data.keyword, items: data.items }] }));
```

改為（覆蓋、只留最新）：

```tsx
        if (event === "jobs") setSearch({ keyword: data.keyword, items: data.items });
```

- [ ] **Step 4: 移除訊息流裡的 jobsBlocks 渲染（`ChatPage.tsx`）**

刪除 assistant 訊息內渲染 `m.jobsBlocks?.map(...)` 的整段（約 224-233 行）：

```tsx
                {m.jobsBlocks?.map((b, j) => (
                  <Stack key={j} gap={6} w="100%" maw="92%">
                    <Group gap={6}>
                      <IconSearch size={13} style={{ color: "var(--mantine-color-dark-2)" }} />
                      <Text size="xs" c="dimmed">搜尋：{b.keyword}</Text>
                    </Group>
                    {b.items.length === 0 && <Text size="xs" c="dimmed">找不到符合的職缺</Text>}
                    {b.items.map((job) => <JobRow key={job.code} job={job} canMatch={canMatch} tracked={trackedCodes.has(job.code)} />)}
                  </Stack>
                ))}
```

（`IconSearch`、`JobRow` 仍會用於右欄面板，import 保留。）

- [ ] **Step 5: `clear()` 一併清 search（`ChatPage.tsx`）**

在 `clear()` 成功清空後（`setMsgs([]);` 之後）加：

```tsx
      setMsgs([]);
      setSearch(null);
```

- [ ] **Step 6: 聊天視窗包進帶邊框容器 ＋ 更新標題（`ChatPage.tsx`）**

把左欄 `PageHeader` 的 title/subtitle 改為：

```tsx
        <PageHeader title="求職總指揮" subtitle="邊聊邊整理履歷與偏好、找職缺、追蹤管道；動作需按套用才生效" />
```

把訊息 `ScrollArea`（`<ScrollArea h=...>...</ScrollArea>`）用 `Paper` 包起來給明確邊框（`ScrollArea` 原樣放進 `Paper` 內）：

```tsx
        <Paper withBorder radius="md" bg="dark.7" p="xs" style={{ overflow: "hidden" }}>
          <ScrollArea h="calc(100vh - 360px)" mih={320} viewportRef={viewport} type="auto">
            <Stack gap="md" pr="sm">
              {/* …既有訊息渲染內容原樣… */}
            </Stack>
          </ScrollArea>
        </Paper>
```

（高度由 `calc(100vh - 330px)` 調為 `calc(100vh - 360px)` 補償 Paper 內距/邊框；訊息 `Stack` 內容原樣不動。）

- [ ] **Step 7: 右欄加寬成雙區（結果上／記憶下）（`ChatPage.tsx`）**

把右欄 `Paper`（`w={280}`）改為 `w={360}`，並在既有「半永久記憶」內容**之上**插入「搜尋結果」區。整個右欄 `Paper` 內容結構改為：

```tsx
      <Paper bg="dark.6" radius="md" p="md" w={360} style={{ flexShrink: 0 }}>
        {/* 搜尋結果區 */}
        <Group gap={6} mb="sm">
          <IconSearch size={15} style={{ color: "var(--mantine-color-dark-2)" }} />
          <Text size="sm" fw={600}>搜尋結果{search ? `：${search.keyword}` : ""}</Text>
        </Group>
        {!search && <Text size="xs" c="dimmed" mb="md">（agent 搜尋後，結果會出現在這）</Text>}
        {search && search.items.length === 0 && <Text size="xs" c="dimmed" mb="md">找不到符合的職缺</Text>}
        {search && search.items.length > 0 && (
          <Stack gap={6} mb="md">
            {search.items.map((job) => (
              <JobRow key={job.code} job={job} canMatch={canMatch} tracked={trackedCodes.has(job.code)} />
            ))}
          </Stack>
        )}
        <Divider mb="sm" />
        {/* 半永久記憶區（原有內容原樣搬到這） */}
        <Group justify="space-between" mb="sm">
          <Group gap={6}>
            <IconBrain size={15} style={{ color: "var(--mantine-color-grape-4)" }} />
            <Text size="sm" fw={600}>半永久記憶</Text>
          </Group>
          <Group gap={2}>
            <ActionIcon variant="subtle" color="gray" size="sm" component="a" href="/api/export" title="匯出求職檔案 MD">
              <IconDownload size={14} />
            </ActionIcon>
            <ActionIcon variant="subtle" color="red" size="sm" onClick={clear} title="清空對話（記憶不清）">
              <IconTrash size={14} />
            </ActionIcon>
          </Group>
        </Group>
        <Stack gap={6}>
          {(history.data?.memory ?? []).map((f, i) => (
            <Group key={i} justify="space-between" wrap="nowrap" gap={4}>
              <Text size="xs" style={{ flex: 1 }}>{f.text}</Text>
              <ActionIcon size="xs" variant="subtle" color="red" onClick={() => removeFact(i)} title="移除這條記憶">
                <IconX size={11} />
              </ActionIcon>
            </Group>
          ))}
          {(history.data?.memory ?? []).length === 0 && (
            <Text size="xs" c="dimmed">（尚無記憶——聊天中提到的長期偏好會自動記在這）</Text>
          )}
        </Stack>
      </Paper>
```

（新增 `Divider` 需在 `@mantine/core` import 補上；`IconSearch`/`IconBrain`/`IconDownload`/`IconTrash`/`IconX` 皆既有 import。）

- [ ] **Step 8: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（`tsc -b && vite build` 無型別/未用 import 錯誤；`jobsBlocks` 已無殘留引用）

- [ ] **Step 9: Commit**

```bash
git add sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天搜尋結果移到右欄面板 + 聊天視窗邊框 + 標題求職總指揮"
```

---

## Self-Review

**Spec coverage：**
- #1 get_job_detail 工具（`_execute_job_detail`＋TOOLS＋`_execute_tool` 分派＋prompt 說明）→ Task 1 ✅
- #2 搜尋結果側邊面板（search state 覆蓋、移除 jobsBlocks、右欄加寬雙區）→ Task 2 ✅
- #3 聊天視窗邊框 ＋ 標題求職總指揮 → Task 2 ✅
- Global Constraints（唯讀無 mutation、SSE 契約不改、只留最新、token 控制、相容）各 Task 遵守 ✅

**Placeholder scan：** 無 TBD/TODO；每個改碼步驟含完整程式碼與確切指令。

**Type consistency：** `_execute_job_detail(code_or_url) -> (None, str, bool)`、`_JD_DESC_MAX`、`get_job_detail` 工具名於 chat/測試/分派一致；前端 `search` state 型別 `{keyword, items: RecommendedJob[]} | null` 於 jobs 事件/面板渲染一致；`jobsBlocks` 於 UiMsg/SSE/渲染三處一併移除無殘留。
