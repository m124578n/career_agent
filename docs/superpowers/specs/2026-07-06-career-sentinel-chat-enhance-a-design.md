# 聊天總指揮增能 A（介面＋讀取批）設計

**日期：** 2026-07-06
**狀態：** 設計定案，待實作

## 這是什麼

career-sentinel 聊天總指揮（SP21 第一階段）之後的增能批次 A——三個相對輕、低風險、不花 LLM 錢的項目：
1. **`get_job_detail` 唯讀工具**：讓 agent 在對話中抓取指定 104 職缺的完整 JD（職務內容/需求），供回答/比較/建議。
2. **搜尋結果側邊面板**：agent `search_jobs` 搜到的職缺改放聊天頁右欄的專門面板，不再塞在聊天訊息流裡（只留最新一次搜尋）。
3. **聊天視窗視覺界線**：聊天訊息區用明確容器邊框框起來；順手把頁面標題「整理助手」更新為「求職總指揮」。

較大的批 B（拖檔＋貼網址分析、客製化＋連 104，屬 LLM 花錢動作 ≈SP21b）不在本篇。

## 目標

一句話：**加一個 `get_job_detail` 唯讀工具、把搜尋結果移到右欄專門面板（只留最新一次）、給聊天視窗明確邊框並更新頁面標題。**

## 現況（實作依據）

- **`chat.py`**：`TOOLS`（search_jobs、get_pipeline）；`_execute_tool(name, tool_input, db_path)` 分派（search_jobs→`_execute_search`；get_pipeline→`_pipeline_tool_json`；未知→is_error）；`build_system_prompt(...)` 的工具說明段介紹 search_jobs/get_pipeline；`JOBS_RESULT_LIMIT = 8`。
- **`jobfetch.py`**：`extract_job_code(url) -> str`（非 104 網址 raise ValueError「請貼 104 職缺網址」）；`fetch_job_detail(code, *, session=None) -> JobDetail`（curl_cffi 公開抓取、需真網路、**不需登入瀏覽器**、不單測——測試以 monkeypatch mock）。
- **`JobDetail`（models.py）**：title/company/salary/location/description/work_exp/education/majors（list）/specialties（list）。
- **前端 `ChatPage.tsx`**：兩欄 `Group`——左欄 `Stack`（`PageHeader title="整理助手"` ＋ `ScrollArea h="calc(100vh - 330px)"` 訊息區 ＋ 輸入 `Group`），右欄 `Paper bg="dark.6" w={280}`（半永久記憶＋匯出/清空鈕）。搜尋結果目前在每則 assistant 訊息的 `m.jobsBlocks` 內 **inline 用 `JobRow` 渲染**（見 224-233 行）。`jobs` SSE 事件在 `send()` 的 SSE 迴圈中 `patchLast((m) => ({ ...m, jobsBlocks: [...(m.jobsBlocks ?? []), { keyword, items }] }))`（約 158 行）。`trackedCodes`/`canMatch` 供 JobRow。
- **SSE 契約（`web/app.py` `/api/chat`）**：`jobs` 事件 payload `{keyword, items:[{code,url,title,company,salary,is_watched}]}`。**本批不改後端 SSE 契約**。

## 後端變更（項目 1：get_job_detail）

### `chat.py` — TOOLS 加 get_job_detail

```python
{
    "name": "get_job_detail",
    "description": "抓取指定 104 職缺的完整 JD（職務內容、需求條件、薪資、地點）。可傳 job code 或 104 職缺網址。回答職缺問題、比較職缺、給客製化建議前用它讀 JD。",
    "input_schema": {
        "type": "object",
        "properties": {"code_or_url": {"type": "string", "description": "104 job code 或職缺網址"}},
        "required": ["code_or_url"],
    },
}
```

### `chat.py` — 執行體與分派

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

`_execute_tool` 加分派（get_pipeline 分支之後、未知工具之前）：

```python
    if name == "get_job_detail":
        return _execute_job_detail(str((tool_input or {}).get("code_or_url", "")))
```

### `chat.py` — build_system_prompt 工具說明加 get_job_detail

工具說明段（介紹 search_jobs/get_pipeline 那段）補一句：`get_job_detail 讀指定職缺的完整 JD（傳 code 或網址；回答職缺細節、比較、給建議前先讀）。`

## 前端變更（項目 2、3）

### `ChatPage.tsx` — 搜尋結果移到右欄專門面板（只留最新）

- 新 state：`const [search, setSearch] = useState<{ keyword: string; items: RecommendedJob[] } | null>(null);`
- SSE `jobs` 事件處理改為 `setSearch({ keyword: data.keyword, items: data.items });`（**覆蓋、只留最新**），移除原本寫入 `m.jobsBlocks` 的 `patchLast`。
- 移除訊息流裡渲染 `m.jobsBlocks` 的整段（224-233 行）；`UiMsg` 的 `jobsBlocks` 欄位與相關型別一併移除（清乾淨）。
- `clear()` 時一併 `setSearch(null)`（清空對話也清結果）。

### `ChatPage.tsx` — 右欄加寬成雙區（結果上／記憶下）

- 右欄 `Paper` 由 `w={280}` 改為 `w={360}`；內容改為上下兩區：
  - **搜尋結果區**（在記憶區之上）：標頭 `🔍 搜尋結果`＋關鍵字；`search` 為 null 顯示「（agent 搜尋後，結果會出現在這）」；否則列 `JobRow`（`items.length === 0` 顯示「找不到符合的職缺」）。沿用既有 `JobRow`（傳 `canMatch`/`tracked={trackedCodes.has(job.code)}`）。
  - **半永久記憶區**（現有內容原樣搬到下方）。
- 兩區之間用 `Divider` 或間距區隔。

### `ChatPage.tsx` — 聊天視窗視覺界線 ＋ 標題

- 把左欄的訊息 `ScrollArea` 包進 `Paper`（`withBorder radius="md" bg="dark.7"`，內距 `p="md"`），讓聊天視窗有明確邊框容器；輸入 `Group` 可留在容器內底部或緊接其下（擇一，維持既有互動）。
- `PageHeader` 的 `title="整理助手"` 改為 `title="求職總指揮"`；subtitle 更新為貼近總指揮定位（如「邊聊邊整理履歷與偏好、找職缺、追蹤管道；動作需按套用才生效」）。

## Global Constraints（實作時必守）

- **唯讀、無 mutation**：`get_job_detail` 只讀（curl 公開抓取），不寫任何狀態、不寫 104、不需登入瀏覽器；與 search_jobs/get_pipeline 同屬工具迴圈自動跑的唯讀工具。
- **後端 SSE 契約不改**：`jobs` 事件 payload 不動；只改前端呈現位置（訊息流→右欄面板）。
- **只留最新一次搜尋**：`search` state 覆蓋式，不累積。
- **token 控制**：`get_job_detail` 的 description 截斷 `_JD_DESC_MAX=1500`；回精簡 JSON（不含 raw）。
- **相容**：`get_job_detail` 為加法工具；既有 search_jobs/get_pipeline 行為與既有 SSE 事件不變；移除 jobsBlocks 後既有 suggestions/remembered/forgot 卡片渲染不受影響。
- 後端測試用專案 venv `sentinel/.venv/Scripts/python.exe -m pytest -q`；前端 `npm run build` 必過（移除 jobsBlocks 後清乾淨殘留型別/import）。

## 測試策略

- **`_execute_job_detail`**（mock `jobfetch.fetch_job_detail` 與 `extract_job_code`）：
  - 傳 code → 回 `(None, json, False)`，JSON 含 title/company/description 等；description 超過 `_JD_DESC_MAX` 被截斷。
  - 傳 104 網址 → 先 extract_job_code 再抓；回正確 code。
  - 傳非 104 網址（extract_job_code raise ValueError）→ `is_error=True`、含提示。
  - 空字串 → `is_error=True`「缺少…」。
  - `fetch_job_detail` 拋例外 → `is_error=True`「抓取…失敗」。
- **`_execute_tool` 分派**：name="get_job_detail" → 呼叫 `_execute_job_detail`；既有 search_jobs/get_pipeline/未知工具分派不變。
- **`build_system_prompt`**：工具說明含 `get_job_detail`（既有 search_jobs/get_pipeline 斷言維持）。
- **`stream_with_tools`**（既有 FakeClient 模式）：一輪 get_job_detail tool_use（mock `_execute_job_detail`）→ 不 yield jobs 事件、回 tool_result；既有 search/get_pipeline 測試不回歸。
- **前端**：無單元測試，靠 `npm run build` ＋人工；契約由後端測試守。

## 明確不做（Out of Scope）

- 批 B：拖檔上傳＋貼網址做履歷/職缺分析（網址不限 104，需通用抓取）、客製化履歷/求職信＋連 104 → 之後獨立 spec（LLM 花錢動作，走確認卡）。
- get_job_detail 支援非 104 網址 → 不做（本工具是 104 專用；通用抓取留批 B）。
- 搜尋結果累積歷史、結果面板排序/篩選 → 不做。
- 既有 UI/UX 其他精修。
