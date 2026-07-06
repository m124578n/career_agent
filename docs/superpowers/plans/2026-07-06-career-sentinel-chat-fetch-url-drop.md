# 聊天拖檔＋貼網址分析（#4）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 加 `fetch_url` 唯讀工具（104→結構化 JD、非 104→通用 HTML 去標籤，抓不到就請使用者貼文字），並讓聊天視窗支援拖放履歷檔上傳為作用中履歷。

**Architecture:** 對話式讀取取徑——不做獨立花錢分析動作。後端在既有 tool use 迴圈加唯讀 `fetch_url`（104 委派既有 `_execute_job_detail`；非 104 用 curl_cffi 抓 HTML＋stdlib 去標籤截斷）。前端聊天視窗加原生 drag-drop，拖進 .pdf/.txt 走既有 `/api/resume/upload` 設為作用中履歷；分析＝agent 讀完在對話裡談。

**Tech Stack:** Python（curl_cffi + stdlib re/html）；React 18 + Mantine 7 + TanStack Query。

## Global Constraints

- **唯讀、無 mutation**：`fetch_url` 只讀，不寫狀態、不寫 104；與 search_jobs/get_pipeline/get_job_detail 同屬工具迴圈自動跑的唯讀工具。
- **通用抓取 best-effort、誠實 fallback**：非 104 抓 HTML 去標籤；抓不到/太短（JS 頁面）→ is_error 明確請使用者貼文字。
- **不加新相依**：通用去標籤用 stdlib `re`＋`html.unescape`；拖放用原生 DOM 事件；不引入 BeautifulSoup/@mantine/dropzone。
- **token 控制**：通用文字截斷 `_FETCH_URL_MAX=3000`；104 路徑沿用 `_JD_DESC_MAX`。
- **拖檔＝作用中履歷**：拖進 `.pdf/.txt` 走既有 `/api/resume/upload`；非支援格式提示；**不自動送訊息**。
- **使用者發起**：fetch_url 由使用者貼網址觸發（本機單人，SSRF 風險可接受）。
- **相容**：`fetch_url`/拖放皆加法；既有工具、SSE、卡片、上傳流程不變。
- **測試指令（後端）**：於 `sentinel/` 用 `./.venv/Scripts/python.exe -m pytest -q`（預設 shell python 缺 pytest，勿用）。
- **測試指令（前端）**：於 `sentinel/web/frontend/` 用 `npm run build`。

---

## File Structure

- `sentinel/src/career_sentinel/chat.py` — 加 `_html_to_text`、`_execute_fetch_url`、常數、`TOOLS` 加 fetch_url、`_execute_tool` 分派、build_system_prompt 說明（Task 1）。
- `sentinel/tests/test_chat_tools.py` — fetch_url 測試（Task 1）。
- `sentinel/web/frontend/src/ChatPage.tsx` — 聊天視窗拖放上傳（Task 2）。

---

### Task 1: `fetch_url` 唯讀工具（後端）

**Files:**
- Modify: `sentinel/src/career_sentinel/chat.py`
- Test: `sentinel/tests/test_chat_tools.py`

**Interfaces:**
- Consumes: 既有 `_execute_job_detail(code_or_url)`（104 → JD JSON）、`jobfetch.extract_job_code`、`curl_cffi.requests.get`。
- Produces:
  - `chat._FETCH_URL_MAX = 3000`、`chat._html_to_text(html_text: str) -> str`。
  - `chat._execute_fetch_url(url: str) -> tuple[None, str, bool]`。
  - `chat.TOOLS` 含 `fetch_url`；`_execute_tool` 分派 fetch_url。

- [ ] **Step 1: 寫失敗測試**

在 `sentinel/tests/test_chat_tools.py` 末尾加：

```python
def test_html_to_text_strips():
    html = ('<html><head><style>.x{color:red}</style></head><body>'
            '<script>var a=1;</script><h1>職缺</h1><p>需要 &amp; Python</p></body></html>')
    t = chat._html_to_text(html)
    assert "職缺" in t and "Python" in t and "&" in t
    assert "color:red" not in t and "var a" not in t and "<" not in t


def test_execute_fetch_url_generic(monkeypatch):
    import curl_cffi.requests as creq_mod
    class FakeResp:
        text = "<html><body><h1>資深後端工程師</h1><p>負責 API 開發</p></body></html>"
        def raise_for_status(self): pass
    monkeypatch.setattr(creq_mod, "get", lambda *a, **k: FakeResp())
    event, text, is_error = chat._execute_fetch_url("https://example.com/jobs/1")
    assert event is None and is_error is False
    data = json.loads(text)
    assert data["url"] == "https://example.com/jobs/1"
    assert "資深後端工程師" in data["text"] and "API" in data["text"]


def test_execute_fetch_url_truncates(monkeypatch):
    import curl_cffi.requests as creq_mod
    class FakeResp:
        text = "<p>" + ("x" * 5000) + "</p>"
        def raise_for_status(self): pass
    monkeypatch.setattr(creq_mod, "get", lambda *a, **k: FakeResp())
    _, text, _ = chat._execute_fetch_url("https://example.com/x")
    assert len(json.loads(text)["text"]) == chat._FETCH_URL_MAX


def test_execute_fetch_url_104_delegates(monkeypatch):
    from career_sentinel import jobfetch
    from career_sentinel.models import JobDetail
    monkeypatch.setattr(jobfetch, "fetch_job_detail",
                        lambda code, **kw: JobDetail(title="後端", description="做後端"))
    event, text, is_error = chat._execute_fetch_url("https://www.104.com.tw/job/9zzz9")
    assert is_error is False
    data = json.loads(text)
    assert data["code"] == "9zzz9" and data["title"] == "後端"  # 走 _execute_job_detail 的 JSON


def test_execute_fetch_url_empty_is_error():
    event, text, is_error = chat._execute_fetch_url("  ")
    assert is_error is True and "缺少" in text


def test_execute_fetch_url_non_http_is_error():
    event, text, is_error = chat._execute_fetch_url("ftp://x")
    assert is_error is True


def test_execute_fetch_url_fetch_failure(monkeypatch):
    import curl_cffi.requests as creq_mod
    def boom(*a, **k):
        raise RuntimeError("網路掛")
    monkeypatch.setattr(creq_mod, "get", boom)
    event, text, is_error = chat._execute_fetch_url("https://example.com/x")
    assert is_error is True and "抓取網頁失敗" in text


def test_execute_fetch_url_js_page_is_error(monkeypatch):
    import curl_cffi.requests as creq_mod
    class FakeResp:
        text = "<html><body></body></html>"  # 去標籤後幾乎空
        def raise_for_status(self): pass
    monkeypatch.setattr(creq_mod, "get", lambda *a, **k: FakeResp())
    event, text, is_error = chat._execute_fetch_url("https://spa.example.com/job")
    assert is_error is True and "JavaScript" in text


def test_execute_tool_fetch_url_dispatch(monkeypatch):
    monkeypatch.setattr(chat, "_execute_fetch_url", lambda u: (None, '{"ok":1}', False))
    event, text, is_error = chat._execute_tool("fetch_url", {"url": "https://x"}, None)
    assert event is None and text == '{"ok":1}' and is_error is False


def test_system_prompt_mentions_fetch_url():
    from career_sentinel.models import JobPreferences, MemoryState, ResumeState, Settings
    p = chat.build_system_prompt(ResumeState(), Settings(), JobPreferences(), MemoryState())
    assert "fetch_url" in p
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: FAIL（`_html_to_text`/`_execute_fetch_url`/`_FETCH_URL_MAX` 不存在；prompt 無 fetch_url）

- [ ] **Step 3: 加 stdlib import 與 `_html_to_text`（`chat.py`）**

`chat.py` 頂部 import 區（`import json` 附近）加：

```python
import html as _html
import re as _re
```

在 `_execute_job_detail` 附近（或 `_execute_search` 之後）加常數與 helper：

```python
_FETCH_URL_MAX = 3000  # 通用抓取文字截斷（控 token）
_SCRIPT_STYLE_RE = _re.compile(r"<(script|style)[^>]*>.*?</\1>", _re.DOTALL | _re.IGNORECASE)
_TAG_RE = _re.compile(r"<[^>]+>")
_WS_RE = _re.compile(r"[ \t\r\f\v]+")
_MULTINL_RE = _re.compile(r"\n{3,}")


def _html_to_text(html_text: str) -> str:
    """粗略把 HTML 轉純文字：去 script/style、去標籤、還原 entity、收斂空白。"""
    t = _SCRIPT_STYLE_RE.sub(" ", html_text or "")
    t = _TAG_RE.sub(" ", t)
    t = _html.unescape(t)
    t = _WS_RE.sub(" ", t)
    t = _MULTINL_RE.sub("\n\n", t)
    return t.strip()
```

- [ ] **Step 4: 加 `_execute_fetch_url`（`chat.py`）**

在 `_html_to_text` 之後加：

```python
def _execute_fetch_url(url: str):
    """fetch_url 執行體。回 (None, result_text, is_error)。唯讀、需真網路。
    104 職缺網址走結構化 JD；其他網址通用抓取去標籤。"""
    raw = (url or "").strip()
    if not raw:
        return None, "缺少網址", True
    if not raw.startswith(("http://", "https://")):
        return None, "請提供有效網址（http/https 開頭）", True
    from . import jobfetch
    try:
        jobfetch.extract_job_code(raw)   # 是 104 職缺網址就走結構化 JD
        return _execute_job_detail(raw)
    except ValueError:
        pass
    try:
        from curl_cffi import requests as creq
        resp = creq.get(raw, impersonate="chrome", timeout=30)
        resp.raise_for_status()
        html_text = resp.text
    except Exception:
        return None, "抓取網頁失敗，請確認網址或直接貼上內容文字", True
    text = _html_to_text(html_text)
    if len(text) < 50:
        return None, "這頁可能需要 JavaScript 才顯示內容，抓不到；請直接貼上職缺內容文字", True
    return None, json.dumps({"url": raw, "text": text[:_FETCH_URL_MAX]}, ensure_ascii=False), False
```

- [ ] **Step 5: `TOOLS` 加 fetch_url ＋ `_execute_tool` 分派（`chat.py`）**

`TOOLS` list 末尾（get_job_detail 之後）加：

```python
    {
        "name": "fetch_url",
        "description": "讀取任意網址的內容（職缺頁、文章等）。使用者貼上網址要你看或分析時用。104 職缺會回結構化 JD；其他網站回去標籤後的純文字。若是需要 JavaScript 才顯示的頁面可能抓不到，會請使用者改貼文字。",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "要讀取的網址（http/https）"}},
            "required": ["url"],
        },
    },
```

`_execute_tool` 在 get_job_detail 分支之後、未知工具 return 之前加：

```python
    if name == "fetch_url":
        return _execute_fetch_url(str((tool_input or {}).get("url", "")))
```

- [ ] **Step 6: build_system_prompt 工具說明加 fetch_url（`chat.py`）**

把工具說明段（現含 search_jobs/get_pipeline/get_job_detail）在 get_job_detail 之後補一句：

```python
        "工具：search_jobs 用關鍵字搜尋 104 職缺（使用者明確要找才用，關鍵字精簡 2–4 個詞）；"
        "get_pipeline 讀你目前的求職管道（要引用或操作既有職缺前，先用它確認 code 與現況）；"
        "get_job_detail 讀指定職缺的完整 JD（傳 code 或網址；回答職缺細節、比較、給建議前先讀）；"
        "fetch_url 讀任意網址內容（使用者貼網址要你看/分析職缺時用；非 104 站也可）。工具呼叫請節制。\n\n"
```

- [ ] **Step 7: 跑測試，確認通過**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest tests/test_chat_tools.py -q`
Expected: PASS（含既有 search/get_pipeline/get_job_detail/prompt 測試）

- [ ] **Step 8: 全套回歸**

Run: `cd sentinel && ./.venv/Scripts/python.exe -m pytest -q`
Expected: PASS（全綠）

- [ ] **Step 9: Commit**

```bash
git add sentinel/src/career_sentinel/chat.py sentinel/tests/test_chat_tools.py
git commit -m "feat(sentinel): fetch_url 唯讀工具（聊天讀任意網址；非104通用抓取）（#4）"
```

---

### Task 2: 聊天視窗拖放上傳履歷（前端）

**Files:**
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`

**Interfaces:**
- Consumes: 既有 `uploadResume(file) -> Promise<Response>`（回 `{chars}`；非支援格式後端 400）；TanStack Query `["resume"]`。

- [ ] **Step 1: 補 import（`ChatPage.tsx`）**

`./api` import 加 `uploadResume`（在既有清單內加）：

```tsx
import {
  applyUpdate, clearChat, deleteMemory, getChat, getResume, getSnapshot, openApplyPage, readSse,
  sendChat, SuggestedUpdate, tailorApplication, uploadResume, type RecommendedJob, type TailoredApplication,
} from "./api";
```

- [ ] **Step 2: 加 state 與 `handleDropFile`（`ChatPage.tsx`）**

在既有 state 宣告區（`const [search, setSearch] = ...` 附近）加：

```tsx
  const [dragActive, setDragActive] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
```

在 `clear` 函式附近加：

```tsx
  const handleDropFile = async (file: File) => {
    const name = file.name.toLowerCase();
    if (!name.endsWith(".pdf") && !name.endsWith(".txt")) {
      setUploadNote("只支援 PDF / TXT 履歷檔");
      return;
    }
    setUploadNote("上傳中…");
    try {
      const r = await uploadResume(file);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setUploadNote(body.detail ?? "上傳失敗"); return; }
      setUploadNote(`已設為作用中履歷：${file.name}（${body.chars} 字）`);
      qc.invalidateQueries({ queryKey: ["resume"] });
    } catch { setUploadNote("網路錯誤，請重試"); }
  };
```

- [ ] **Step 3: 聊天視窗 Paper 加拖放事件與視覺提示（`ChatPage.tsx`）**

把聊天視窗容器那行：

```tsx
        <Paper withBorder radius="md" bg="dark.7" p="xs" style={{ overflow: "hidden" }}>
```

改為（加拖放事件＋dragActive 時邊框變 teal）：

```tsx
        <Paper withBorder radius="md" bg="dark.7" p="xs"
          style={{ overflow: "hidden", borderColor: dragActive ? "var(--mantine-color-teal-5)" : undefined }}
          onDragOver={(e) => { e.preventDefault(); if (!dragActive) setDragActive(true); }}
          onDragLeave={(e) => { e.preventDefault(); setDragActive(false); }}
          onDrop={(e) => {
            e.preventDefault(); setDragActive(false);
            const f = e.dataTransfer.files?.[0];
            if (f) handleDropFile(f);
          }}>
```

- [ ] **Step 4: 加拖放提示 ＋ 上傳結果 Alert（`ChatPage.tsx`）**

在聊天視窗容器 `</Paper>`（`</ScrollArea>` 之後那個 `</Paper>`）與輸入 `<Group wrap="nowrap">` 之間插入：

```tsx
        {dragActive && <Text size="xs" c="teal.5">放開以上傳履歷（PDF / TXT）</Text>}
        {uploadNote && (
          <Alert color="gray" variant="light" withCloseButton onClose={() => setUploadNote(null)} py={6}>
            {uploadNote}
          </Alert>
        )}
```

（`Alert`、`Text` 皆既有 import。）

- [ ] **Step 5: build 驗證**

Run: `cd sentinel/web/frontend && npm run build`
Expected: 成功（`tsc -b && vite build` 無型別/未用 import 錯誤）

- [ ] **Step 6: Commit**

```bash
git add sentinel/web/frontend/src/ChatPage.tsx
git commit -m "feat(sentinel): 聊天視窗拖放上傳履歷（設為作用中履歷）（#4）"
```

---

## Self-Review

**Spec coverage：**
- #4b fetch_url（_html_to_text 去標籤、_execute_fetch_url 104 委派/通用抓取/空/非http/失敗/JS 頁面、TOOLS、分派、prompt）→ Task 1 ✅
- #4a 聊天拖檔 → 作用中履歷（drag-drop、.pdf/.txt 檢查、uploadResume、note、不自動送）→ Task 2 ✅
- Global Constraints（唯讀無 mutation、best-effort fallback、不加相依、token 控制、拖檔=作用中履歷、相容）各 Task 遵守 ✅

**Placeholder scan：** 無 TBD/TODO；每步含完整程式碼與確切指令。

**Type consistency：** `_execute_fetch_url(url) -> (None, str, bool)`、`_FETCH_URL_MAX`、`_html_to_text(html_text) -> str`、`fetch_url` 工具名於 chat/測試/分派一致；前端 `dragActive`/`uploadNote` state 與 handleDropFile/Paper 事件/Alert 一致；`uploadResume` 回 `{chars}` 與 note 使用一致。
