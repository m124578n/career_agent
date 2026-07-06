# 聊天總指揮增能 #4：聊天拖檔＋貼網址分析 設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 聊天總指揮的增能項目 #4（LLM 花錢批的最後一個）：讓 agent 能在對話中做**履歷分析／職缺分析**。採**對話式讀取工具**取徑——不做獨立的花錢分析動作卡，而是給 agent 兩個能力，「分析」＝ agent 讀完在對話裡談（＝正常聊天）：
1. **`fetch_url` 唯讀工具**：讀任意網址（**網址不限 104**）——104 職缺走既有結構化 JD、其他網站通用抓取去標籤。
2. **聊天拖檔上傳**：把履歷檔拖進聊天視窗 → 上傳成為作用中履歷 → agent 隨即可分析。

## 目標

一句話：**加 `fetch_url` 唯讀工具（104→結構化 JD、非 104→通用 HTML 去標籤，抓不到就請使用者貼文字），並讓聊天視窗支援拖放履歷檔上傳為作用中履歷。**

## 現況（實作依據）

- **`chat.py`**：`TOOLS`（search_jobs、get_pipeline、get_job_detail）；`_execute_tool(name, tool_input, db_path)` 分派；`_execute_job_detail(code_or_url)`（104 code/url → `fetch_job_detail` → JSON brief，含截斷 `_JD_DESC_MAX`）；`build_system_prompt` 工具說明段。
- **`jobfetch.py`**：`extract_job_code(url) -> str`（非 104 raise ValueError）；`fetch_job_detail(code)`（curl_cffi）。curl 慣例：`creq.Session(impersonate="chrome", timeout=30)` / `creq.get(url, impersonate="chrome", timeout=30)`、`resp.text`/`resp.raise_for_status()`。
- **相依**：`curl_cffi`（抓取）、`pypdf`（PDF）。**無 BeautifulSoup/readability**——通用去標籤用 stdlib（`re` + `html.unescape`）。
- **`/api/resume/upload`（既有）**：`resume.parse_resume(filename, bytes)` → 存 `resume_text`、`source="upload"`、回 `{chars}`。前端 `uploadResume(file) -> Promise<Response>`。
- **前端 `ChatPage.tsx`**：聊天訊息區已包在 `Paper withBorder`（增能 A）；輸入 `Group`；右欄搜尋結果/記憶面板。TanStack Query `["resume"]`。

## 後端變更（#4b：`fetch_url` 工具，`chat.py`）

### HTML 去標籤 helper

```python
import html as _html
import re as _re

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

### 執行體與分派

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

`_execute_tool` 加分派（get_job_detail 分支之後、未知工具之前）：

```python
    if name == "fetch_url":
        return _execute_fetch_url(str((tool_input or {}).get("url", "")))
```

### TOOLS 加 fetch_url

```python
{
    "name": "fetch_url",
    "description": "讀取任意網址的內容（職缺頁、文章等）。使用者貼上網址要你看或分析時用。104 職缺會回結構化 JD；其他網站回去標籤後的純文字。若是需要 JavaScript 才顯示的頁面可能抓不到，會請使用者改貼文字。",
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "要讀取的網址（http/https）"}},
        "required": ["url"],
    },
}
```

### build_system_prompt 工具說明加 fetch_url

工具說明段在 get_job_detail 之後補一句：`fetch_url 讀任意網址內容（使用者貼網址要你看/分析職缺時用；非 104 站也可）。`

## 前端變更（#4a：聊天拖檔 → 作用中履歷，`ChatPage.tsx`）

- 新 state：`const [dragActive, setDragActive] = useState(false);`、`const [uploadNote, setUploadNote] = useState<string | null>(null);`。
- 把聊天視窗容器（訊息區的 `Paper withBorder`）加拖放事件：
  - `onDragOver`：`e.preventDefault(); setDragActive(true);`
  - `onDragLeave`：`setDragActive(false);`
  - `onDrop`：`e.preventDefault(); setDragActive(false);` 取 `e.dataTransfer.files[0]`，交給 `handleDropFile`。
  - `dragActive` 時容器加視覺提示（如邊框變 teal、顯示「放開以上傳履歷」覆蓋層）。
- `handleDropFile(file)`：
  - 副檔名非 `.pdf`/`.txt` → `setUploadNote("只支援 PDF / TXT 履歷檔")`。
  - 否則 `uploadResume(file)`：`!r.ok` → 顯示 `body.detail`；`r.ok` → 讀 `{chars}` → `setUploadNote(\`已設為作用中履歷：${file.name}（${chars} 字）\`)`＋`qc.invalidateQueries({ queryKey: ["resume"] })`。
  - **不自動送訊息**（成本由使用者控制；上傳後使用者自行打「幫我分析履歷」）。
- `uploadNote` 用 `Alert`（可關）顯示在輸入列上方。
- import 補 `uploadResume`（api.ts 既有）。

## Global Constraints（實作時必守）

- **唯讀、無 mutation**：`fetch_url` 只讀（curl 抓取），不寫狀態、不寫 104；與 search_jobs/get_pipeline/get_job_detail 同屬工具迴圈自動跑的唯讀工具。
- **通用抓取 best-effort、誠實 fallback**：非 104 站抓 HTML 去標籤；抓不到/太短（JS 頁面）→ is_error 明確請使用者貼文字，不硬掰。
- **不加新相依**：通用去標籤用 stdlib `re`＋`html.unescape`；拖放用原生 DOM 事件；不引入 BeautifulSoup/@mantine/dropzone。
- **token 控制**：`fetch_url` 通用文字截斷 `_FETCH_URL_MAX=3000`；104 路徑沿用 `_JD_DESC_MAX`。
- **拖檔＝作用中履歷**：拖進 `.pdf/.txt` 走既有 `/api/resume/upload`（設 `source="upload"`）；非支援格式提示；不自動送訊息。
- **使用者發起**：fetch_url 由使用者貼網址觸發（本機單人，SSRF 風險可接受，不主動掃描）。
- **相容**：`fetch_url`/拖放皆加法；既有 get_job_detail/search_jobs/get_pipeline、SSE、既有卡片與上傳流程不變。
- 後端測試用專案 venv；前端 `npm run build` 必過。

## 測試策略

- **`_html_to_text`**（純函式）：含 `<script>`/`<style>`/標籤/entity（如 `&amp;`）的 HTML → 去 script/style、去標籤、還原 entity、收斂空白；純文字進出穩定。
- **`_execute_fetch_url`**：
  - 非 104 網址（mock `curl_cffi.requests.get` 回一個 `.text` 有內容、`.raise_for_status()` 不拋的假 resp）→ `(None, json, False)`，JSON 含 `url` 與去標籤 `text`（截斷 `_FETCH_URL_MAX`）。
  - 104 職缺網址（mock `jobfetch.fetch_job_detail`）→ 委派 `_execute_job_detail`，回結構化 JD JSON（含 code/title）。
  - 空 url → is_error「缺少網址」；非 http → is_error。
  - `curl_cffi.get` 拋例外 → is_error「抓取網頁失敗…」。
  - 去標籤後 `< 50` 字（JS 頁面）→ is_error「需要 JavaScript…請直接貼上」。
- **`_execute_tool` 分派**：name="fetch_url" → 呼叫 `_execute_fetch_url`；既有 search/get_pipeline/get_job_detail 分派不變。
- **`build_system_prompt`**：工具說明含 `fetch_url`（既有工具斷言維持）。
- **前端**：無單元測試，靠 `npm run build` ＋人工（拖 PDF → 顯示「已設為作用中履歷」、拖非支援檔提示、貼網址讓 agent fetch_url）。

## 明確不做（Out of Scope）

- 一次性履歷材料（不覆蓋作用中）、多檔上傳、圖片/JD OCR → 不做。
- JS 頁面的瀏覽器渲染抓取（playwright）→ 不做（誠實 fallback 請貼文字）。
- 專用分析結果卡、把抓到的 JD 存成 tracked job → 不做（對話式即可；要追蹤仍走既有 track 提議）。
- 貼網址自動觸發前端動作 → 不做（使用者把網址打進訊息，agent 自行用 fetch_url）。
