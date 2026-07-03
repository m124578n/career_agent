# career-sentinel SP10：聊天中即時推職缺（工具呼叫架構）設計

> 日期：2026-07-03。狀態：使用者已核可設計，待 plan。
> 前情：SP1–SP9 完成、211 測試綠。provider 現況＝Foundry 單家（SP9 spike 確認，LLM_API_KEY 空）。

## 目標

整理助手聊天中，使用者**明確要求**找職缺（「幫我找 Python 後端」）時，LLM 透過
**原生 Anthropic tool use** 呼叫既有站內搜尋，職缺卡片直接嵌入聊天訊息流、
LLM 並引用結果給出評論。

## 關鍵決策（使用者選定）

- **架構＝原生 Anthropic tool use**（非擴充 `<suggestions>` 通道、非關鍵字按鈕）。
  只實作 Foundry 路徑（現況唯一 provider）；OpenAI 相容路徑照舊純聊天不掛工具（未測、spec 註明）。
- **觸發＝使用者明示才搜**（system prompt 明訂；LLM 不得聊到相關就主動搜）。

## 工具迴圈（後端核心）

### `chat.py` 擴充
- 新函式 `stream_with_tools(messages, *, system, client=None) -> Iterator[dict]`：
  Foundry SDK `client.messages.stream(model, max_tokens, system, messages, tools=TOOLS)`；
  - 迭代 stream：文字增量 yield `{"type": "text", "text": ...}`（照常給 StreamFilter 過濾外流）。
  - `stop_reason == "tool_use"`：取出 tool_use blocks → 逐一執行 →
    yield `{"type": "jobs", "keyword": ..., "items": [...]}`（給 SSE）→
    把 assistant content（含 tool_use）與 `tool_result`（user role）附回 messages →
    **再開下一段串流**。
  - **迴圈上限 `TOOL_LOOP_MAX = 2`**：達上限後最後一輪不帶 tools（強制作答）。
- provider 分派：`llm_provider() == "foundry"` 走工具迴圈；`"openai"` 走既有
  `llm.chat_stream`（無工具、行為與 SP8 相同）；無 key raise 既有 RuntimeError。

### 工具定義（唯一工具）
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
```
- 執行器：既有 `scraper.search.fetch_search(keyword)`（curl_cffi 公開端點，快、無瀏覽器依賴）。
  **「推薦」不掛**（headful＋瀏覽器忙碌鎖，不適合聊天內即時呼叫）。
- `tool_result` 給 LLM **精簡 JSON**（title/company/salary/url，**最多 8 筆**）供評論篩選；
  完整清單（含 code、is_watched 標記）走 SSE 給前端。
- 搜尋失敗：`tool_result` 帶 `is_error: true` 與錯誤說明文字（LLM 轉告使用者），串流不中斷。

### 與既有機制的關係
- **`<suggestions>` 尾端通道原封不動**（建議更新／memory remember/forget 照舊）——
  tool use 只管搜尋，兩機制並存，不重構 SP8。
- `StreamFilter`／訊息持久化（乾淨文字）／compact／memory 整理全部不變。
- system prompt 追加工具規則：「只在使用者明確要求找職缺時呼叫 search_jobs；
  關鍵字精簡（2–4 個詞）；每輪對話至多 2 次」。

## SSE 協議擴充（`web/app.py`）

- 新事件 `jobs`：`{"keyword": str, "items": [{code,url,title,company,salary,is_watched}]}`；
  每次工具執行後立即發，**可與 `delta` 交錯**（多次搜尋多個 jobs 事件）。
- 事件序：`delta*/jobs*` 交錯 → `suggestions?` → `remembered?` → `forgot?` → `done`；
  例外 → `error` 後結束（既有行為）。
- items 的 `is_watched` 用既有 `watch.is_watched`＋settings 標記。

## 前端（ChatPage）

- `UiMsg` 加 `jobsBlocks?: { keyword: string; items: RecommendedJob[] }[]`；
  `jobs` 事件 append 到當前助手訊息（平滑打字機 pending 機制同步擴充：jobs 到達即掛，
  不等文字 drain 完——卡片位置在該則訊息下方區塊，不打斷打字機）。
- 渲染：「🔎 搜尋：{keyword}」小標（IconSearch＋Text）＋**重用既有 `JobRow`**
  （聊天內職缺直接有「比對」「查評價 🔍」「去 104 看」完整功能）；
  `canMatch` 由 ChatPage 以 `useQuery(["resume"])` 提供。
- 卡片**不持久化**（重開 serve／重載頁面消失——同建議卡片既有慣例）。
- 空結果：渲染「找不到符合的職缺」dimmed 文字（LLM 也會在文字中說明）。

## 邊界（YAGNI）

- 不掛「推薦」工具、不做多工具、不做 OpenAI 相容路徑的 tools、
  不持久化卡片、不做搜尋結果分頁。
- PII：送 LLM 的仍是既有聊天內容＋搜尋關鍵字/結果（公開資料），不新增出口類型。

## 測試（全假 client，不打真 LLM／真 104）

- `stream_with_tools`：假 Anthropic stream 兩段腳本（第一段文字+tool_use、
  第二段引用結果作答）→ 驗事件序（text/jobs/text）、messages 追加結構（assistant+tool_result）、
  迴圈上限（連續 tool_use 到第 3 次不再帶 tools）、tool 失敗 is_error 路徑。
- executor：monkeypatch `fetch_search` 驗精簡化（8 筆上限、欄位）與失敗轉 is_error。
- `/api/chat` SSE：假 stream 驗 `delta/jobs/done` 交錯序＋jobs payload 形狀（含 is_watched）。
- 前端 build 零 TS 錯誤。
- 真機：聊天說「幫我找 Python 後端的職缺」→ 卡片出現＋LLM 評論；卡片上比對/查評價可用；
  一般整理對話不觸發搜尋。
