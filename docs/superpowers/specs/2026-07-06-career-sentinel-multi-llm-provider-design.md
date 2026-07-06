# 多 LLM Provider 設計（暫緩實作）

**日期：** 2026-07-06
**狀態：** ⏸️ 設計決策已定，**暫緩實作**——使用者目前沒有這些端點的 API key 可測試。等有 key 再進 writing-plans → SDD。

## 這是什麼

career-sentinel 的 LLM 層目前有兩條 provider 路徑（`config.llm_provider()` 依 env 偵測）：
- **foundry**：Anthropic on Azure Foundry（`AnthropicFoundry`）——**唯一**有原生 tool-use 聊天總指揮（`chat.stream_with_tools`）＋ web search（`web_search_20250305`）。
- **openai**：任何 OpenAI 相容端點（`LLM_BASE_URL`）——`parse_json` ＋ `chat_stream`；聊天**退化成無工具純聊天**（`app._chat_events` 對 non-foundry 走 `llm.chat_stream`，不帶工具）。

要多加 provider：**Anthropic 直連、Google Gemini、明確的 OpenAI 相容預設（OpenAI/OpenRouter/Groq/Together）、本機 Ollama/LM Studio**。

## Provider 表面（要覆蓋的呼叫點）

| 呼叫點 | 用途 | 現況 |
|---|---|---|
| `llm.parse_json` | 結構化 JSON（比對/健檢/客製化/議價 JSON） | openai / foundry 分派 |
| `llm.chat_stream` | 純聊天串流 | openai / foundry 分派 |
| `research.web_search_complete` | web 搜尋（公司研究/議價） | openai `_openai_research` / foundry `_foundry_research`（Anthropic web_search 工具） |
| `chat.stream_with_tools` | **聊天總指揮原生 tool-use 迴圈**（search_jobs/get_pipeline/get_job_detail/fetch_url ＋ suggestions） | **僅 foundry** |

## 已定決策

1. **整併成兩條真實轉接層：**
   - **Anthropic 家族**（`foundry` ＋ `anthropic` 直連）：共用同一套 anthropic SDK 的 parse_json/chat_stream/web-search/**stream_with_tools**，只差建 client 的 factory：`AnthropicFoundry(api_key, base_url)` vs `Anthropic(api_key)`。→ Anthropic 直連可**完整支援**原生 tool-use 總指揮 ＋ web search，工作量低（共用 foundry 路徑）。
   - **OpenAI 相容**（`openai`）：涵蓋 OpenAI 直連 / OpenRouter / Groq / Together / 本機 Ollama / LM Studio / **Gemini（走其 OpenAI 相容端點）**，差別只在 `base_url` / `model`。

2. **明確 `LLM_PROVIDER` 選擇器**（env）：值 `foundry` / `anthropic` / `openai`。**向下相容**——未設時沿用現有 presence-based 偵測（有 `FOUNDRY_API_KEY`→foundry、否則有 `LLM_API_KEY`→openai）。

3. **非 Anthropic provider 也要原生工具使用** → 給 openai 路徑加一條 **OpenAI function-calling 工具迴圈**（對應 `stream_with_tools` 的工具集：search_jobs/get_pipeline/get_job_detail/fetch_url），讓搜尋職缺/讀管道/確認卡在 OpenAI 相容 ＋ Gemini provider 上也能用。體驗一致。**（本分支最大工作量）**

4. **Gemini 走 OpenAI 相容端點**（`generativelanguage.googleapis.com/v1beta/openai/`）當成 openai preset，**不寫新 SDK**。

5. **預設選單（presets）**：常用 provider 給 `base_url`/`model` 一鍵切換（放 `.env.example` ＋ config presets）：OpenAI、OpenRouter、Groq、Together、Ollama（`http://localhost:11434/v1`）、LM Studio（`http://localhost:1234/v1`）、Gemini-OpenAI 端點。

## 待解細節（實作前要拍板）

- **web search 在 OpenAI 相容上的分歧**：OpenRouter 支援 `:online` 後綴；純 OpenAI 有 Responses API 的 web_search 工具；Gemini-OpenAI 端點/Ollama **可能沒有 web search**。→ `web_search_complete` 需 per-provider 處理或**優雅退化**（無 web search 時給明確訊息或退回無搜尋的一般生成）。這關係到議價建議/公司研究在這些 provider 上的可用性。
- **OpenAI function-calling 工具迴圈**與現有 `stream_with_tools`（Anthropic tool_use 格式）並存：抽出共用工具定義（`_execute_tool` 已是 provider 無關），各自做 provider 專屬的 tool schema ＋ 迴圈。結構性終止上限（防無限迴圈）比照現有。
- **env 變數命名**：`LLM_PROVIDER`、既有 `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`、Anthropic 直連用 `ANTHROPIC_API_KEY`（或沿用 `LLM_*`？）。
- **設定 UI**：是否在前端 SettingsModal 露出 provider 切換，或純 `.env`（單人本機，`.env` 可能足夠）。
- **測試**：parse_json/chat_stream/工具迴圈的 provider 分派可用 fake client 單測（不需真 key）；真端點整合測試**需使用者提供 key**（目前卡點）。

## 為何暫緩

使用者目前沒有 Anthropic 直連 / Gemini / OpenRouter 等端點的 API key，無法做真端點驗證。設計先存檔；等取得 key 後：writing-plans → SDD，並可先用 fake-client 單測把分派邏輯做起來，真端點驗證留待 key 到位。

## 明確不做（Out of Scope）

- 原生 google-genai SDK（改走 Gemini 的 OpenAI 相容端點）。
- 每個 provider 的獨立計費/用量細分（沿用現有 usage 記錄）。
- provider 自動 failover / 多 provider 同時。
