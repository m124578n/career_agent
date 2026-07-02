# career-sentinel SP8：對話式履歷/需求整理（整理助手）設計

> 日期：2026-07-02。狀態：使用者已核可設計，待出 plan。
> 前情：SP1–SP7 完成（儀表板/設定/履歷健檢/JD 比對/推薦/搜尋/排程通知/面試行事曆），153 測試綠。

## 目標

新增「整理助手」聊天分頁：使用者用自然語言邊聊邊整理履歷與求職偏好，
LLM 以**串流**回覆並附**結構化建議更新**（建議卡片＋一鍵套用），聊天中自動把值得長期記住的
使用者資訊寫進**半永久 memory**，對話過長時自動 **compact**。

**範圍邊界（本 SP 只到「整理＋寫回本地狀態」）**：聊天中即時推職缺＝SP10、
客製化履歷/求職信＋投遞＋追蹤＝SP11、履歷回寫 104＝SP12（皆已記 roadmap，本 SP 不做）。

## 架構總覽

```
前端「整理助手」分頁                    後端
┌──────────────┐  POST /api/chat(SSE) ┌─────────────────┐
│ 訊息列表＋輸入框 │ ───────────────────→ │ chat.py（服務層）  │
│ 打字機串流顯示   │ ←─ delta / suggestions│  組 system prompt │
│ 建議卡片[套用]  │      / done / error   │ llm.chat_stream() │
│ 🧠已記住徽章    │                       │  截 <suggestions> │
│ memory 側欄    │  POST /api/chat/apply │  →解析→事件        │
└──────────────┘  GET/DELETE /api/chat  └─────────────────┘
                                         SQLite 單列：chat / preferences / memory
```

一次 LLM 呼叫完成「聊天＋建議」（方案 A）：回覆文字邊生邊以 SSE `delta` 事件下發；
LLM 依約定在回覆結尾輸出 `<suggestions>{...JSON...}</suggestions>` 區塊，
後端串流中偵測到開始標記即**截住不外流**，串流結束解析 JSON、驗進 Pydantic、
以 `suggestions` 事件下發；解析失敗＝靜默降級成純聊天（不報錯、不炸）。

## 模組與職責

### `llm.chat_stream(messages, system) -> Iterator[str]`（`llm.py` 新增）
- 多輪對話串流，yield 文字增量。provider-aware（沿用 `llm_provider()` 偵測）：
  - `openai`：`POST {base_url}/chat/completions`、`stream: true`，逐行解析 SSE `data:` 的 `choices[0].delta.content`。
  - `foundry`：`AnthropicFoundry` 的 `messages.stream(...)`，迭代 `text_stream`。
- 無 key：raise（同 `parse_json` 的 RuntimeError pattern）。
- 附帶效益：為技術債「digest 彙整走 provider 層」鋪 `llm.chat` 地基。

### `chat.py`（新服務層模組，純邏輯、可獨立測）
- `build_system_prompt(resume, settings, prefs, memory) -> str`：嵌入履歷摘要、目標職稱/薪資、
  關注清單、求職偏好、半永久 memory facts；並宣告 `<suggestions>` 輸出契約（含欄位白名單與 op 規格）。
- `build_messages(state: ChatState, user_msg: str) -> list[dict]`：`summary`（若非空，作為一則
  system/assistant 前情提要）＋近期逐字訊息＋本輪 user 訊息。
- `StreamFilter`：串流截斷狀態機。逐 chunk 進、吐「可安全外流的文字」；偵測 `<suggestions>` 開始
  標記（**須處理標記跨 chunk 邊界**：尾端保留潛在部分標記不外流）；結束後 `.tail()` 取被截住的原始文字。
- `parse_suggestions(tail: str) -> list[SuggestedUpdate]`：取 `<suggestions>...</suggestions>` 內
  JSON（重用 `llm._extract_json` 韌性），驗進 Pydantic；任何失敗回 `[]`。
- `apply_update(conn, upd: SuggestedUpdate) -> ApplyResult`：欄位白名單分派寫回（見下）；
  回 `{ok, message}`（如 replace_snippet 找不到 old → `ok=False`）。
- `maybe_compact(conn, state) -> ChatState`：見 context 管理。

### `web/app.py` 端點
- `POST /api/chat`，body `{message: str}` → `StreamingResponse`（`text/event-stream`）。
  事件序列：`delta`(多次, `{text}`) → `suggestions`(`{items:[...]}`，可空) →
  `remembered`(`{facts:[...]}`，有自動記憶才發) → `done`；例外 → `error`(`{message}`) 後結束。
  解析出的 `op=remember` 項目**自動寫入 memory 後只走 `remembered` 事件**，
  不出現在 `suggestions.items`（建議卡片只放需要使用者按套用的項目）。
  回覆完成即持久化訊息（user＋assistant 乾淨文字，不含 suggestions 標記），再跑 compact 檢查。
- `POST /api/chat/apply`，body＝一筆 `SuggestedUpdate` → `{ok, message}`。
- `GET /api/chat` → `{summary, messages, memory: [facts]}`（載入歷史＋側欄資料）。
- `DELETE /api/chat` → 清空 `summary`＋`messages`（**memory 不清**）。
- `DELETE /api/memory/{index}` → 刪除單筆 memory fact。
- 無 LLM key：`POST /api/chat` 回 400（同 SP3 pattern），前端顯示引導。

## 資料模型（`models.py` 新增）

```python
class ChatMessage(BaseModel):
    role: str            # "user" | "assistant"
    content: str

class ChatState(BaseModel):
    summary: str = ""                    # 更早對話的壓縮摘要
    messages: list[ChatMessage] = []     # 近期逐字訊息

class JobPreferences(BaseModel):
    locations: list[str] = []    # 想要的工作地點
    conditions: list[str] = []   # 軟條件（遠端、小團隊、成長性…）
    avoid: list[str] = []        # 避雷條件

class MemoryFact(BaseModel):
    text: str
    created_at: str              # ISO

class MemoryState(BaseModel):
    facts: list[MemoryFact] = []

class SuggestedUpdate(BaseModel):
    field: str                   # 白名單，見下
    op: str = "set"              # set | replace_snippet | append_section | remember
    value: str | int | list[str] | None = None   # set 的新值 / append 的段落 / remember 的 text
    old: str | None = None       # replace_snippet 專用
    new: str | None = None       # replace_snippet 專用
```

**欄位白名單與 op 對應**（`apply_update` 只認這些，其餘一律拒絕）：

| field | 允許 op | 寫到 |
|---|---|---|
| `target_title` / `expected_salary` | set | `ResumeState` |
| `locations` / `conditions` / `avoid` | set（整列表取代） | `JobPreferences` |
| `watched_companies` / `watched_keywords` | set（整列表取代） | `Settings` |
| `resume_text` | replace_snippet / append_section | `ResumeState.resume_text` |
| `memory` | remember | `MemoryState`（**自動寫入**，不經套用） |

薪資與職稱**不在 JobPreferences 重複建欄**——沿用 `ResumeState.expected_salary`/`target_title`。

## store（新增三張單列表，同 settings/resume pattern）
- `chat (id=1, data JSON)` ↔ `ChatState`；`preferences (id=1, data JSON)` ↔ `JobPreferences`；
  `memory (id=1, data JSON)` ↔ `MemoryState`。
- `CREATE TABLE IF NOT EXISTS`＝加法式遷移（舊 DB 自動長出新表）。

## context 管理＋compact

- 每輪送 LLM＝system prompt（履歷摘要＋偏好＋memory）＋ `summary` 前情提要＋近期逐字訊息。
- **觸發**：回覆完成、訊息持久化後檢查——`len(messages) > 30` 時，把「最近 10 則以外的全部舊訊息」
  用 LLM 壓成摘要（prompt：合併舊 summary＋這些舊訊息 → 新 summary），只留最近 10 則逐字。
- 門檻常數 `COMPACT_THRESHOLD = 30`、`COMPACT_KEEP = 10`（`chat.py` 模組常數，可調）。
- **安全序**：先成功產出並寫入新 summary，才裁切 messages——compact 失敗（LLM 錯誤）就整個跳過、
  本輪維持原狀、下輪再試，永不弄丟逐字訊息。
- compact 同步在請求尾端執行（單人工具、每 30 則才觸發一次，延遲可接受；不另開背景執行緒）。

## 半永久 memory

- LLM 在同一 `<suggestions>` 通道回 `op=remember`，**自己判斷**哪些使用者資訊值得長期記住
  （如「不想進博弈業」「通勤以雙北為主」）。
- remember **自動寫入** `MemoryState`（低風險、不覆蓋既有資料），即時以 `remembered` SSE 事件
  下發，聊天中顯示「🧠 已記住：…」徽章；其餘 op 一律等使用者按「套用」。
- memory 每輪都進 system prompt、**不受 compact 影響**——compact 丟細節、memory 留結論，這就是「半永久」。
- 管理：聊天分頁側欄列出全部 facts、逐筆可刪（`DELETE /api/memory/{index}`）。「清空對話」不動 memory。

## 前端「整理助手」分頁（第六個 Tab）

- 主聊天區：訊息列表（使用者右、助手左）、打字機串流（fetch `ReadableStream` reader 逐 chunk
  append——EventSource 不支援 POST 故不用）、回覆結束在該則助手訊息下渲染建議卡片
  （欄位名、舊值→新值（resume_text 可展開預覽）、`[套用]` 按鈕→成功打勾／失敗標「無法套用」）、
  `🧠 已記住` 徽章。
- 側欄：memory 清單（逐筆刪）＋「清空對話」（confirm 後 DELETE，memory 不清）。
- 輸入框 Enter 送出；串流中鎖輸入；**網路層一律 try/finally 解鎖**（記取 SP-Search 卡 spinner 教訓）。
- 建議卡片「套用」呼叫 `/api/chat/apply` 後，invalidate 相關 TanStack Query cache
  （resume/settings/preferences），讓其他分頁即時反映。

## 錯誤處理

- 無 LLM key：分頁顯示設定引導（同 SP3）。
- 串流中斷/網路錯誤：已顯示文字保留、該則標「回覆中斷」、輸入解鎖；中斷的回覆**不持久化**
  （避免半句話進歷史）。
- `<suggestions>` JSON 壞掉：`parse_suggestions` 回空、當純聊天。
- `apply` 對 replace_snippet 找不到 `old`：回 `{ok:false}`，卡片顯示「無法套用，請手動修改」。
- 白名單外 field / 未知 op：`/api/chat/apply` 回 400。

## 安全邊界

- 寫回**只走** `/api/chat/apply` 白名單；LLM 無法直接碰白名單外任何狀態；除 remember 外
  每筆建議都要使用者確認。
- PII 出口：聊天把履歷全文＋偏好＋memory 送外部 LLM——與 SP3（本來就送履歷全文）同級，
  不新增出口類型；本地綁定 127.0.0.1 不變。

## 測試策略（延續既有風格：fixture＋假 client/假串流，不打真 LLM）

- `chat.py` 純函式：system prompt 組裝（含 memory/偏好嵌入）、`StreamFilter`
  （**標記跨 chunk 邊界** case、無標記 case、標記後仍有殘文 case）、`parse_suggestions`
  （正常/壞 JSON/缺欄位）、compact 裁切（門檻邊界、失敗跳過不裁切）。
- `llm.chat_stream`：假 httpx client 餵 OpenAI SSE 行 / 假 Anthropic stream，驗 yield 序列。
- store：三張新表 round-trip＋空 DB 預設值。
- API：`/api/chat` SSE 事件序列（monkeypatch 假串流：delta→suggestions→remembered→done）、
  無 key 400、`/api/chat/apply` 每種 field×op（含拒絕 case）、`GET`/`DELETE` 行為、memory 刪除。
- 真機驗證：真 LLM 聊數輪——改薪資（set 套用）、補履歷段落（append）、講出偏好（🧠 記住）、
  清空對話後 memory 仍在、聊超過門檻觸發 compact。

## 不做（YAGNI）
- 多對話管理（單一長期對話＋清空即可）。
- provider 原生 tool-use 串流（SP10 需要工具呼叫時再引入）。
- memory 編輯（只有刪除；要改就刪掉重講）。
- token 精確計數（以訊息「則數」當 compact 門檻）。
