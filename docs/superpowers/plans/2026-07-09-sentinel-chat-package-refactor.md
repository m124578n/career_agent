# sentinel `chat.py` → `chat/` 套件重構 實作計畫（階段 1）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `src/career_sentinel/chat.py`（659 行、~7 職責）拆成 `chat/` 套件的 6 個聚焦子模組，行為零改變，全程維持既有測試綠。

**Architecture:** 採方案 A（套件 + `__init__` 再匯出 facade）。先把整檔搬進 `chat/__init__.py` 並修正相對匯入，再逐一把職責群組抽到子模組、於 `__init__` 以 re-export 保留 `chat.X` 公開面。`web/app.py` 完全不動；僅在工具群組搬出時更新測試的 monkeypatch 目標（`chat` → `chat.tools`）。

**Tech Stack:** Python 3.12、pytest、既有 `career_sentinel` 套件（`llm`/`store`/`pipeline`/`usage`/`models`/`scraper`/`jobfetch`/`config`）。

## Global Constraints

- **行為零改變**：純內部搬移，不改任何執行期邏輯、回傳格式、函式簽名、常數值。
- **方案 A**：`chat/__init__.py` 以 re-export 維持 `from career_sentinel import chat` 後 `chat.X` 的既有存取（含被測試 monkeypatch 的私有函式）。
- **`web/app.py` 不得修改**。
- **測試全程綠**：每個 task 後跑 `./.venv/Scripts/python.exe -m pytest -q`，維持 `400 passed`。
- **不新增行為測試**：正確性由既有 400 測試背書。前端不動。
- **搬移一律 verbatim**：函式/類別/常數本體逐字搬，只調整 import。
- 測試指令一律用專案 venv：`./.venv/Scripts/python.exe -m pytest`（工作目錄 `sentinel/`）。
- 匯入慣例：套件內子模組引用 `career_sentinel` 的兄弟模組用 `from .. import X`；引用同套件子模組用 `from .X import Y`。

---

## 檔案結構（階段 1 終態）

```
src/career_sentinel/chat/
├─ __init__.py        # re-export facade（+ from .. import llm 供 chat.llm）
├─ prompt.py          # 系統提示與訊息組裝
├─ suggestions.py     # <suggestions> 解析 / 串流過濾 / 套用
├─ memory.py          # compact 對話 + curate 記憶
├─ export.py          # 匯出求職檔案 MD
├─ tools.py           # 工具定義與執行
└─ orchestrator.py    # tool-use 串流迴圈
```

（原 `src/career_sentinel/chat.py` 於 Task 1 刪除。）

---

### Task 1: `chat.py` → `chat/__init__.py`（module 轉 package、修正相對匯入）

把整個 `chat.py` 原封搬進新套件的 `__init__.py`，並把所有 `from .` 相對匯入改成 `from ..`（因為模組從 `career_sentinel/chat.py` 變成 `career_sentinel/chat/__init__.py`，`.` 的意義由「career_sentinel」變成「chat 套件」）。此 task 不拆任何職責。

**Files:**
- Create: `src/career_sentinel/chat/__init__.py`（內容 = 原 `chat.py` 全文，相對匯入改 `..`）
- Delete: `src/career_sentinel/chat.py`
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Produces: `career_sentinel.chat` 成為套件；`chat.X` 全數符號不變、行為不變。後續 task 從此 `__init__.py` 往外抽。

- [ ] **Step 1: 建立套件檔並搬入全文**

用 Write 建立 `src/career_sentinel/chat/__init__.py`，內容為現有 `src/career_sentinel/chat.py` 的**逐字全文**，僅套用下列 8 處相對匯入修正（其餘一字不改）：

| 位置（原 chat.py 內） | 原文 | 改為 |
|---|---|---|
| 頂層 | `from . import llm, pipeline, store, usage` | `from .. import llm, pipeline, store, usage` |
| 頂層 | `from .models import (` | `from ..models import (` |
| `apply_update` 內 | `from .models import OfferDetail` | `from ..models import OfferDetail` |
| `apply_update` 內 | `from .models import InterviewNote` | `from ..models import InterviewNote` |
| `_execute_search` 內 | `from .scraper import search as search_mod` | `from ..scraper import search as search_mod` |
| `_execute_fetch_url` 內 | `from . import jobfetch` | `from .. import jobfetch` |
| `_execute_job_detail` 內 | `from . import jobfetch` | `from .. import jobfetch` |
| `stream_with_tools` 內 | `from .config import foundry_settings` | `from ..config import foundry_settings` |

（`from anthropic import AnthropicFoundry`、`from pydantic import BaseModel` 及 stdlib import 不動。）

- [ ] **Step 2: 刪除舊模組檔**

```bash
git rm src/career_sentinel/chat.py
```

- [ ] **Step 3: 快速匯入健檢**

Run: `./.venv/Scripts/python.exe -c "import career_sentinel.chat as c; print(c.build_system_prompt.__module__, c._execute_search.__module__, c.stream_with_tools.__module__)"`
Expected: 印出三個模組名（皆為 `career_sentinel.chat`），無 ImportError / 循環匯入錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/chat/__init__.py
git commit -m "refactor(sentinel): chat.py 轉為 chat/ 套件（修正相對匯入，行為不變）"
```

---

### Task 2: 抽出 `chat/prompt.py`（系統提示與訊息組裝）

**Files:**
- Create: `src/career_sentinel/chat/prompt.py`
- Modify: `src/career_sentinel/chat/__init__.py`（移除已搬走的定義、加入 re-export）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Produces: `prompt.build_system_prompt`、`prompt.build_messages`、`prompt.format_pipeline_summary`（簽名不變）。

- [ ] **Step 1: 建立 `chat/prompt.py`**

用 Write 建立 `src/career_sentinel/chat/prompt.py`，檔頭如下，其後**逐字搬入**這些定義（依原順序）：`_RESUME_MAX_CHARS`、`_PIPE_GROUP_LIMIT`、`_PIPE_STATE_ORDER`、`_PIPE_STATE_LABEL`、`format_pipeline_summary`、`_CONTRACT`、`build_system_prompt`、`build_messages`。

```python
"""求職總指揮：系統提示與訊息組裝。"""
from __future__ import annotations

from datetime import datetime

from ..models import ChatState, JobPreferences, MemoryState, PipelineJob, ResumeState, Settings
```

- [ ] **Step 2: 從 `__init__.py` 移除這些定義並加 re-export**

在 `chat/__init__.py`：刪掉 Step 1 已搬走的那 8 個定義（`_RESUME_MAX_CHARS`、`_PIPE_GROUP_LIMIT`、`_PIPE_STATE_ORDER`、`_PIPE_STATE_LABEL`、`format_pipeline_summary`、`_CONTRACT`、`build_system_prompt`、`build_messages`），並在檔案頂端 import 區塊之後加入：

```python
from .prompt import build_messages, build_system_prompt, format_pipeline_summary  # noqa: F401
```

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "import career_sentinel.chat as c; print(c.build_system_prompt.__module__)"`
Expected: `career_sentinel.chat.prompt`，無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/chat/prompt.py src/career_sentinel/chat/__init__.py
git commit -m "refactor(sentinel): 抽出 chat/prompt.py"
```

---

### Task 3: 抽出 `chat/suggestions.py`（建議解析／串流過濾／套用）

**Files:**
- Create: `src/career_sentinel/chat/suggestions.py`
- Modify: `src/career_sentinel/chat/__init__.py`
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Consumes: 無（自足；`apply_update` 內 `from ..models import OfferDetail`/`InterviewNote` 為函式內 import，隨本體搬移）。
- Produces: `suggestions.StreamFilter`、`suggestions.parse_suggestions`、`suggestions.apply_update`、`suggestions.ApplyResult`。

- [ ] **Step 1: 建立 `chat/suggestions.py`**

用 Write 建立 `src/career_sentinel/chat/suggestions.py`，檔頭如下，其後**逐字搬入**（依原順序）：`SUGGESTIONS_OPEN`、`SUGGESTIONS_CLOSE`、`_partial_marker_len`、`StreamFilter`、`parse_suggestions`、`ALLOWED`、`ApplyResult`、`_as_str_list`、`apply_update`。

```python
"""求職總指揮：<suggestions> 建議區塊的解析、串流過濾與套用。"""
from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel

from .. import llm, store
from ..models import MemoryFact, SuggestedUpdate
```

（`apply_update` 本體內的 `from ..models import OfferDetail` 與 `from ..models import InterviewNote` 保留為函式內 import，一併逐字搬入。）

- [ ] **Step 2: 從 `__init__.py` 移除並加 re-export**

在 `chat/__init__.py`：刪掉 Step 1 已搬走的定義（`SUGGESTIONS_OPEN`、`SUGGESTIONS_CLOSE`、`_partial_marker_len`、`StreamFilter`、`parse_suggestions`、`ALLOWED`、`ApplyResult`、`_as_str_list`、`apply_update`），並加入：

```python
from .suggestions import ApplyResult, StreamFilter, apply_update, parse_suggestions  # noqa: F401
```

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "import career_sentinel.chat as c; print(c.apply_update.__module__, c.StreamFilter.__module__)"`
Expected: 皆為 `career_sentinel.chat.suggestions`，無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/chat/suggestions.py src/career_sentinel/chat/__init__.py
git commit -m "refactor(sentinel): 抽出 chat/suggestions.py"
```

---

### Task 4: 抽出 `chat/memory.py`（compact 對話 + curate 記憶）

**Files:**
- Create: `src/career_sentinel/chat/memory.py`
- Modify: `src/career_sentinel/chat/__init__.py`
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Produces: `memory.maybe_compact`、`memory.maybe_curate_memory`、`memory.CuratedFacts`、常數 `COMPACT_THRESHOLD`/`COMPACT_KEEP`/`CURATE_THRESHOLD`。

- [ ] **Step 1: 建立 `chat/memory.py`**

用 Write 建立 `src/career_sentinel/chat/memory.py`，檔頭如下，其後**逐字搬入**（依原順序）：`COMPACT_THRESHOLD`、`COMPACT_KEEP`、`CURATE_THRESHOLD`、`maybe_compact`、`CuratedFacts`、`maybe_curate_memory`。

```python
"""求職總指揮：對話壓縮（compact）與長期記憶整理（curate）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .. import llm, store
from ..models import ChatState, MemoryFact
```

- [ ] **Step 2: 從 `__init__.py` 移除並加 re-export**

在 `chat/__init__.py`：刪掉 `COMPACT_THRESHOLD`、`COMPACT_KEEP`、`CURATE_THRESHOLD`、`maybe_compact`、`CuratedFacts`、`maybe_curate_memory`，並加入：

```python
from .memory import (  # noqa: F401
    COMPACT_KEEP, COMPACT_THRESHOLD, CURATE_THRESHOLD, CuratedFacts,
    maybe_compact, maybe_curate_memory,
)
```

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "import career_sentinel.chat as c; print(c.maybe_compact.__module__, c.COMPACT_KEEP)"`
Expected: `career_sentinel.chat.memory 10`，無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/chat/memory.py src/career_sentinel/chat/__init__.py
git commit -m "refactor(sentinel): 抽出 chat/memory.py"
```

---

### Task 5: 抽出 `chat/export.py`（匯出求職檔案 MD）

**Files:**
- Create: `src/career_sentinel/chat/export.py`
- Modify: `src/career_sentinel/chat/__init__.py`
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Produces: `export.build_export_md`（簽名不變）。

- [ ] **Step 1: 建立 `chat/export.py`**

用 Write 建立 `src/career_sentinel/chat/export.py`，檔頭如下，其後**逐字搬入** `build_export_md`。

```python
"""求職總指揮：匯出求職檔案 Markdown。"""
from __future__ import annotations

from datetime import datetime

from ..models import ChatState, JobPreferences, MemoryState, ResumeState, Settings
```

- [ ] **Step 2: 從 `__init__.py` 移除並加 re-export**

在 `chat/__init__.py`：刪掉 `build_export_md`，並加入：

```python
from .export import build_export_md  # noqa: F401
```

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "import career_sentinel.chat as c; print(c.build_export_md.__module__)"`
Expected: `career_sentinel.chat.export`，無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: Commit**

```bash
git add src/career_sentinel/chat/export.py src/career_sentinel/chat/__init__.py
git commit -m "refactor(sentinel): 抽出 chat/export.py"
```

---

### Task 6: 抽出 `chat/tools.py`（工具定義與執行）+ 更新測試 monkeypatch 目標

工具函式搬到 `chat/tools.py` 後，測試裡 `monkeypatch.setattr(chat, "_execute_*", …)` 必須改指向 `chat.tools`——因為 `_execute_tool` 在 tools 模組內以模組區域名稱呼叫 `_execute_search` 等，patch 打在 `__init__` 的 re-export 參照上不會生效。此 task 同時完成搬移與測試目標更新，維持綠燈。

**Files:**
- Create: `src/career_sentinel/chat/tools.py`
- Modify: `src/career_sentinel/chat/__init__.py`
- Modify: `tests/test_chat_tools.py`（7 處 monkeypatch 目標）
- 其餘測試不改。

**Interfaces:**
- Consumes: 無（`_execute_search` 內 `from ..scraper import search`、`_execute_*` 內 `from .. import jobfetch` 為函式內 import，隨本體搬移）。
- Produces: `tools.TOOLS`、`tools._execute_search`、`tools._execute_fetch_url`、`tools._execute_job_detail`、`tools._pipeline_tool_json`、`tools._execute_tool`、`tools._html_to_text`、常數 `JOBS_RESULT_LIMIT`/`_FETCH_URL_MAX`/`_JD_DESC_MAX`。

- [ ] **Step 1: 建立 `chat/tools.py`**

用 Write 建立 `src/career_sentinel/chat/tools.py`，檔頭如下，其後**逐字搬入**（依原順序）：`JOBS_RESULT_LIMIT`、`TOOLS`、`_execute_search`、`_FETCH_URL_MAX`、`_SCRIPT_STYLE_RE`、`_TAG_RE`、`_WS_RE`、`_MULTINL_RE`、`_html_to_text`、`_execute_fetch_url`、`_JD_DESC_MAX`、`_execute_job_detail`、`_pipeline_tool_json`、`_execute_tool`。

```python
"""求職總指揮：工具定義與執行（search_jobs / get_pipeline / get_job_detail / fetch_url）。"""
from __future__ import annotations

import html as _html
import json
import re as _re

from .. import pipeline, store
```

（`_execute_search` 內 `from ..scraper import search as search_mod`、`_execute_fetch_url`/`_execute_job_detail` 內 `from .. import jobfetch`、`_execute_fetch_url` 內 `from curl_cffi import requests as creq` 皆保留為函式內 import，逐字搬入。）

- [ ] **Step 2: 從 `__init__.py` 移除並加 re-export**

在 `chat/__init__.py`：刪掉 Step 1 已搬走的 14 個定義。加入：

```python
from .tools import (  # noqa: F401
    JOBS_RESULT_LIMIT, TOOLS, _FETCH_URL_MAX, _JD_DESC_MAX,
    _execute_fetch_url, _execute_job_detail, _execute_search, _execute_tool,
    _html_to_text, _pipeline_tool_json,
)
```

（此時 `__init__.py` 仍保有 `stream_with_tools` 與 `TOOL_LOOP_MAX`；`stream_with_tools` 以裸名參照的 `TOOLS`、`_execute_tool` 皆已由上面 re-export 進 `__init__` 命名空間，可正常解析。）

- [ ] **Step 3: 更新測試的 monkeypatch 目標（`tests/test_chat_tools.py`）**

把下列 7 處的 `monkeypatch.setattr(chat, …)` 改為 `monkeypatch.setattr(chat.tools, …)`（lambda / 函式本體不變）：

1. `test_stream_with_tools_happy_path` — `chat` → `chat.tools`（`_execute_search`）
2. `test_stream_with_tools_loop_limit` — `chat` → `chat.tools`（`_execute_search`）
3. `test_stream_with_tools_error_no_jobs_event` — `chat` → `chat.tools`（`_execute_search`）
4. `test_execute_tool_search_dispatch` — `chat` → `chat.tools`（`_execute_search`）
5. `test_execute_tool_search_dispatch_passes_page` — `chat` → `chat.tools`（`_execute_search`）
6. `test_execute_tool_get_job_detail_dispatch` — `chat` → `chat.tools`（`_execute_job_detail`）
7. `test_execute_tool_fetch_url_dispatch` — `chat` → `chat.tools`（`_execute_fetch_url`）

範例（第 6 處）：

```python
    monkeypatch.setattr(chat.tools, "_execute_job_detail", lambda x: (None, '{"ok":1}', False))
```

（`chat.tools` 可存取：`__init__` 的 `from .tools import …` 已把 `tools` 綁為 `chat` 套件屬性。其餘 patch `creq_mod`/`jobfetch` 等外部模組的測試不需更動。）

- [ ] **Step 4: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "import career_sentinel.chat as c; print(c._execute_tool.__module__, c.tools._execute_search.__module__)"`
Expected: 皆為 `career_sentinel.chat.tools`，無錯誤。

- [ ] **Step 5: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 6: Commit**

```bash
git add src/career_sentinel/chat/tools.py src/career_sentinel/chat/__init__.py tests/test_chat_tools.py
git commit -m "refactor(sentinel): 抽出 chat/tools.py（並更新測試 monkeypatch 目標為 chat.tools）"
```

---

### Task 7: 抽出 `chat/orchestrator.py` + 收斂 `__init__.py` 為最終 facade

**Files:**
- Create: `src/career_sentinel/chat/orchestrator.py`
- Modify: `src/career_sentinel/chat/__init__.py`（改寫為最終 re-export shim）
- Test: 既有 `tests/`（不修改）

**Interfaces:**
- Consumes: `from .tools import TOOLS, _execute_tool`。
- Produces: `orchestrator.stream_with_tools`、`orchestrator.TOOL_LOOP_MAX`。

- [ ] **Step 1: 建立 `chat/orchestrator.py`**

用 Write 建立 `src/career_sentinel/chat/orchestrator.py`，檔頭如下，其後**逐字搬入** `stream_with_tools`（`TOOL_LOOP_MAX` 移到檔頭常數區）。

```python
"""求職總指揮：Foundry 原生 tool-use 串流編排迴圈。"""
from __future__ import annotations

from .. import llm, usage
from .tools import TOOLS, _execute_tool

TOOL_LOOP_MAX = 4  # 每輪對話最多執行幾次工具
```

（`stream_with_tools` 本體內 `from ..config import foundry_settings` 與 `from anthropic import AnthropicFoundry` 保留為函式內 import，逐字搬入。本體不變。）

- [ ] **Step 2: 改寫 `chat/__init__.py` 為最終 facade**

用 Write 覆寫 `src/career_sentinel/chat/__init__.py` 為下列完整內容：

```python
"""求職總指揮服務層：prompt 組裝、建議解析/套用、compact/記憶整理、工具執行、tool-use 編排。

實作拆到子模組（prompt/suggestions/memory/export/tools/orchestrator）；此處再匯出公開面，
維持 `from career_sentinel import chat` 後 `chat.X` 的既有存取（含被測試 monkeypatch 的私有函式）。
"""
from __future__ import annotations

from .. import llm  # noqa: F401 — 對外相容：chat.llm
from .export import build_export_md  # noqa: F401
from .memory import (  # noqa: F401
    COMPACT_KEEP, COMPACT_THRESHOLD, CURATE_THRESHOLD, CuratedFacts,
    maybe_compact, maybe_curate_memory,
)
from .orchestrator import TOOL_LOOP_MAX, stream_with_tools  # noqa: F401
from .prompt import build_messages, build_system_prompt, format_pipeline_summary  # noqa: F401
from .suggestions import ApplyResult, StreamFilter, apply_update, parse_suggestions  # noqa: F401
from .tools import (  # noqa: F401
    JOBS_RESULT_LIMIT, TOOLS, _FETCH_URL_MAX, _JD_DESC_MAX,
    _execute_fetch_url, _execute_job_detail, _execute_search, _execute_tool,
    _html_to_text, _pipeline_tool_json,
)
```

- [ ] **Step 3: 匯入健檢**

Run: `./.venv/Scripts/python.exe -c "import career_sentinel.chat as c; print(c.stream_with_tools.__module__, c.TOOL_LOOP_MAX, c.llm.__name__)"`
Expected: `career_sentinel.chat.orchestrator 4 career_sentinel.llm`，無錯誤。

- [ ] **Step 4: 跑全套測試**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: `400 passed`

- [ ] **Step 5: 確認 `app.py` 未被改動且可載入**

Run: `git status --porcelain src/career_sentinel/web/app.py`（應無輸出）與 `./.venv/Scripts/python.exe -c "from career_sentinel.web.app import create_app; create_app()"`
Expected: 前者無輸出（app.py 零改動）；後者無錯誤。

- [ ] **Step 6: Commit**

```bash
git add src/career_sentinel/chat/orchestrator.py src/career_sentinel/chat/__init__.py
git commit -m "refactor(sentinel): 抽出 chat/orchestrator.py，__init__ 收斂為 facade"
```

---

## Self-Review

**1. Spec coverage：** spec 階段 1 表列的 6 子模組與符號分配，逐一對應 Task 2–7；`__init__` re-export（含 `chat.llm`）於 Task 7 定稿；「app.py 不動、測試只改 monkeypatch 目標」對應 Global Constraints 與 Task 6 Step 3；「維持 400 綠」為每 task 的驗證步。無遺漏。

**2. Placeholder scan：** 無 TBD/TODO；每個搬移步驟列出確切符號與確切檔頭 import；測試改動列出確切 7 個函式與範例。

**3. Type/名稱一致性：** 子模組檔頭 import 僅含各自本體實際用到的符號——`prompt`（datetime + 6 models）、`suggestions`（json/datetime/BaseModel/llm/store/MemoryFact/SuggestedUpdate；OfferDetail/InterviewNote 為函式內 import）、`memory`（datetime/BaseModel/llm/store/ChatState/MemoryFact）、`export`（datetime + 5 models）、`tools`（html/json/re/pipeline/store；scraper/jobfetch/curl_cffi 為函式內 import）、`orchestrator`（llm/usage + `.tools` 的 TOOLS/_execute_tool；config/anthropic 為函式內 import）。`__init__` 最終 re-export 名單涵蓋所有被 `app.py`（`chatmod.*`）與測試（`chat.*`，含 `_execute_*`/`_pipeline_tool_json`/`_html_to_text`/`CuratedFacts`/常數/`llm`）存取的符號。一致。
