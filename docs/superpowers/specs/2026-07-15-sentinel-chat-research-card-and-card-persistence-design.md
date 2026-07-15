# sentinel 聊天：agent 查公司評價卡 + 確認卡持久化 — 設計

**日期**：2026-07-15
**範圍**：地端 `sentinel/` 子專案的求職總指揮聊天（`chat/` + `web/routers/chat.py` + `web/frontend/src/ChatPage.tsx`）。
**部署注意**：sentinel 是地端子專案，merge main **不觸發線上部署**。驗收＝`pytest -q` 全綠 + `web/frontend` `npm run build` 通過。

## 目標

1. **Part A**：讓聊天 agent 能提議「查公司評價」（`research_company`）——比照現有 negotiate/客製化/面試準備的「確認卡」模式：agent 丟卡片、使用者按下才上網查（花 web search 錢）。
2. **Part B**：把聊天的**確認卡（含已按過的生成結果）持久化**，重載聊天後卡片與其結果都還在，不再消失。

## 使用者決定（已確認）

- Part A 觸發＝**確認卡**（非自動工具），與 negotiate 等一致，花費由使用者按下才發生。
- Part B＝**連生成結果也存**（重載後直接看到上次生成的客製化內容/公司評價/議價/面試準備）。

## 現況（沿用）

- 聊天串流：`chat_send`（SSE）跑 provider → `StreamFilter` 把 `<suggestions>` 區塊從外流文字剝掉、只把乾淨文字存進 `ChatMessage.content`；`parse_suggestions` 解析出 `SuggestedUpdate` 清單，memory 類即時套用，其餘（cards）**只用 SSE `suggestions` 事件即時送前端、未持久化**。
- `ChatMessage`＝`{role, content}`；`ChatState`＝`{summary, messages}`；`store.save_chat/load_chat` 以 `model_dump_json/model_validate_json` 存取（**加預設欄位向後相容**）。
- 前端 `ChatPage` 載入（`getChat`）時只 map `{role, content}`，丟掉 suggestions；run 卡（TailorCard/NegotiateCard/InterviewPrepCard）結果存在元件 `useState`，重載即失。
- run 卡不在 `suggestions.ALLOWED`、不走 `apply_update`，純由前端渲染＋按下執行。
- 各功能結果原本就有各自快取：research→`store.save_research`(7天)、tailor→`tracked_jobs.tailor_json`、interview_prep→`tracked_jobs.interview_prep_json`；negotiate 無快取。**本設計不依賴這些快取**，改採「把結果存進聊天狀態」的統一機制（見 Part B）。
- `maybe_compact`（`chat/memory.py`）：超過門檻時把較舊訊息壓成 summary、只留最近數則 → 被壓掉的訊息其卡片/結果應一併清理。

## Part A：agent 查公司評價確認卡

### 資料/後端
- **不新增端點**：重用 `GET /api/research?company=&force=`（已含 7 天快取與 provider 檢查）。
- **`chat/prompt.py` `_CONTRACT`**：新增一種提議
  `{"field": "research", "op": "run", "payload": {"company": "華碩"}}`，並加規則：
  - 使用者想了解某公司評價/風評/值不值得去時提議；`payload.company` 取自對話或管道中的公司名，不得杜撰。
  - 這是**提議**，按下才實際上網查（花 LLM＋web search 錢）；**agent 不得自行編造公司評價或聲稱已查**，只丟提議卡。
- **`build_system_prompt`**：能力清單補一句「使用者想了解某公司評價時，可提議『查公司評價』卡」。
- **`suggestions.py` 不改**（research 是前端 run 卡，不進 `ALLOWED`）。

### 前端
- 從 `ResearchButton.tsx` **抽出共用 `ResearchView`**（呈現 summary/風險 badge/優缺點/薪資/面試/來源，比照 `NegotiateButton.tsx` 匯出 `NegotiationView` 的模式）；`ResearchButton` 改用它，行為不變。
- `ChatPage` 新增 `ResearchCard`（照 `NegotiateCard`）：按鈕呼叫 `getResearch(payload.company)`，成功後以 `ResearchView` 呈現。
- render switch（`ChatPage` 卡片分派）加分支：`s.field === "research"` → `ResearchCard`。

## Part B：確認卡（含結果）持久化

### 資料模型（`models.py`）
- `SuggestedUpdate` 加 `card_id: str = ""`（持久化時指派 uuid；live 亦帶同一 id）。
- `ChatMessage` 加 `suggestions: list[SuggestedUpdate] = Field(default_factory=list)`。
- `ChatState` 加 `card_results: dict[str, dict] = Field(default_factory=dict)`（`card_id` → run 卡生成結果的序列化 dict）。

### 後端（`web/routers/chat.py`）
- `chat_send` 產生 `cards` 後，**逐張指派 `card_id = uuid4().hex`**（同一批 id 同時用於：SSE `suggestions` 事件、存進 assistant `ChatMessage.suggestions`）。存訊息改為
  `ChatMessage(role="assistant", content="".join(clean_parts), suggestions=cards)`。
- 新端點 `POST /api/chat/card-result`，body `{card_id: str, result: dict}`：
  - `card_id` 空 → 400；載入 chat、`st.card_results[card_id] = result`、`save_chat`；回 `{ok: true}`。
  - 只存不驗證 result 結構（各卡自負其型別）；為控大小，`result` 上限（如序列化 > 20000 字）→ 截拒 400。
- `chat_get` 回傳新增 `card_results`（`st.card_results`）。
- **孤兒清理**：`maybe_compact` 產生 `new_state` 時，`card_results` 只保留仍被 `recent` 訊息 `suggestions[].card_id` 參照的鍵（避免無限增長）。

### 前端（`api.ts` / `ChatPage.tsx`）
- `api.ts`：`SuggestedUpdate` 型別加 `card_id?: string`；`ChatMessage` 型別加 `suggestions?: SuggestedUpdate[]`；`getChat` 回傳型別加 `card_results: Record<string, any>`；新增 `saveCardResult(card_id, result)` → `POST /api/chat/card-result`。
- `ChatPage`：
  - 載入（現行 line 339）改 map `suggestions: m.suggestions`；並把 `history.data.card_results` 放入可供卡片查詢的來源（state）。
  - run 卡（Tailor/Negotiate/InterviewPrep/Research）改為接 `cardId` 與 `initialResult`：
    - `initialResult` 存在（來自 `card_results[card_id]`）→ 初始化 `result`，重載直接顯示、不顯示按鈕。
    - 執行成功後呼叫 `saveCardResult(cardId, result)` 持久化。
  - render switch 傳入 `cardId={s.card_id}` 與 `initialResult={cardResults[s.card_id]}`。
- **apply 卡**（SuggestionCard：track/job_offer/interview_note/偏好…）：一樣帶 `card_id`、重載後重現（可再次套用；不追蹤「已套用」狀態，見非目標）。

### LLM 界線（重要約束）

- **`suggestions` 與 `card_results` 一律不進 LLM prompt**。`build_messages` 只取每則訊息的
  `role` + `content`；`content` 維持 `StreamFilter` 剝除 `<suggestions>` 後的乾淨文字。
  新增欄位純供 UI 重建與持久化，**不得**被序列化進 `content` 或塞入 `build_messages`，
  以免增加 token／費用。實作與測試須守住此界線（可加一條測試：帶 `card_results` 的
  `ChatState` 經 `build_messages` 後，輸出訊息不含結果內容）。

## 資料流

- **live**：`chat_send` → 產 cards + 指派 card_id → SSE `suggestions`（含 card_id）→ 前端渲染卡；同批 cards 存進 assistant 訊息。使用者按 run 卡 → 呼叫既有端點（如 `/api/research`、`/api/tailor`）取得結果 → `saveCardResult(card_id, result)` 寫回 `ChatState.card_results`。
- **重載**：`chat_get` 回 messages（含 `suggestions` 帶 card_id）＋`card_results` → 前端重建卡片；有 `card_results[card_id]` 的直接以對應 View 呈現結果。

## 錯誤處理

- `POST /api/chat/card-result`：card_id 空／result 過大 → 400；未知 card_id 仍存（可能屬尚未落地的 live 卡；由 compact 清孤兒）。
- research/tailor 等執行失敗沿用既有卡片內錯誤顯示與重試。
- 舊聊天資料（無新欄位）載入 → 預設空，卡片區塊自然為空，不報錯。

## 測試

- 後端（`tests/`）：
  - `ChatMessage`/`ChatState` 帶 `suggestions`/`card_results` 經 `save_chat`→`load_chat` round-trip 保留。
  - `parse_suggestions` 能解析 `research/run` 提議為 `SuggestedUpdate`（Part A）。
  - `POST /api/chat/card-result`：存入後 `GET /api/chat` 回傳含該 `card_results`；card_id 空→400、result 過大→400。
  - `chat_send` 一輪（mock provider 產出帶 `<suggestions>` 的回覆）後 `load_chat`：assistant 訊息 `suggestions` 非空且每張有 `card_id`（沿用 `tests/test_web_chat.py` 既有 mock 方式）。
  - `maybe_compact` 壓縮後，`card_results` 只留仍被保留訊息參照的鍵。
- 前端：`npm run build`。

## 非目標（YAGNI）

- 不追蹤 apply 卡「已套用/已按過」狀態（重載後仍可再按；套用多為冪等）。
- 不做 run 卡結果的版本歷史／多次結果保留（`card_results[card_id]` 只留最後一次）。
- 不改 negotiate/tailor/interview_prep 既有端點的計費或快取行為；不新增 negotiate 快取（結果統一走 `card_results` 持久化）。
- Part A 不做「自動工具」式即時查詢（使用者已選確認卡）。
