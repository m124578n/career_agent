# career-sentinel SP13：Token 用量與花費追蹤（側欄左下角）設計

> 日期：2026-07-04。狀態：使用者已核可設計，直接進 plan → subagent 開發。
> 前情：SP1–SP12 完成、backlog 清空、240 測試綠。本 SP 為使用者新需求。

## 目標

側欄左下角常駐顯示累計 token 用量與預估 USD 花費；並以一張 log 記錄「哪個功能各花多少
token（input/output/cache）」，可看逐功能明細、可歸零。

## 使用者決策（已定）

- **累計方式**：永久累計（存 SQLite）＋可歸零。重開 serve 仍累計。
- **log 記錄**：每次 LLM 呼叫記一列——功能名／模型／input／output／cache／換算 USD。
- **定價來源**：程式內定價表（`_PRICING` 常數），可調；預設套 Claude Sonnet 官方單價。

## 定價（`_PRICING` 預設，$/M tokens）

以 Claude Sonnet 4.5（使用者 Foundry 模型系）Anthropic 官方單價為預設：

| 欄位 | 單價 $/M | 來源 |
|---|---|---|
| input | 3.00 | Sonnet 官方 |
| output | 15.00 | Sonnet 官方 |
| cache_write（5m） | 3.75 | 1.25 × input |
| cache_read | 0.30 | 0.1 × input |

- **注意**：使用者 provider 是 Microsoft Foundry，實際計費可能與 Anthropic 直連不同；`_PRICING`
  寫在常數、易改。定價不準是已知取捨（使用者選「程式內可調」）。
- `_PRICING` 為 dict：模型名 substring → `{"in", "out", "cache_read", "cache_write"}`。
  預設含一筆 `"sonnet"` → 上表，及一筆 fallback `"default"` → 同 sonnet 值。
- `_price_for(model: str) -> dict`：對 model 小寫做 substring 比對，命中回該筆，否則回 `"default"`。

## 後端

### 資料表（`store.py` 建表，隨 `init_db` 建立）

```sql
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feature TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    at TEXT NOT NULL
)
```

### 新模組 `usage.py`

- `_PRICING` / `_price_for(model)`：如上。
- `cost_of(model, input_tokens, output_tokens, cache_read, cache_write) -> float`：
  各類 token × 對應單價 / 1_000_000 加總。
- `normalize(raw) -> dict`：把兩家 provider 的 usage 正規化成
  `{"input", "output", "cache_read", "cache_write"}`（皆 int，缺的當 0）。
  - Anthropic（Foundry）：物件有 `input_tokens`/`output_tokens`/`cache_creation_input_tokens`/
    `cache_read_input_tokens`（用 `getattr(raw, name, 0)`；也接受 dict 用 `.get`）。
    **Anthropic 的 `input_tokens` 不含 cache**——直接對應 `input`。
  - OpenAI：dict 有 `prompt_tokens`/`completion_tokens`，cache 於
    `prompt_tokens_details.cached_tokens`（可能無）。OpenAI 的 `prompt_tokens` **含** cache 部分，
    故 `input = prompt_tokens - cached`、`cache_read = cached`、`cache_write = 0`（OpenAI 無明確 write 計費欄）。
- `record(feature, model, raw) -> None`：**best-effort，整段 try/except 吞掉**（記帳失敗絕不影響
  LLM 呼叫）。流程：`n = normalize(raw)` → `cost = cost_of(model, …)` → 自開連線
  （`store.connect(config.db_path())` 或現有連線工廠）→ INSERT 一列（`at` = ISO now）→ close。
  raw 為 None 或 normalize 全 0 仍記（記錄該次呼叫發生；成本 0）。
- `summary(conn) -> dict`：`{"total_tokens", "total_usd", "by_feature": [...]}`。
  - `total_tokens` = SUM(input+output+cache_read+cache_write)；`total_usd` = SUM(cost_usd)。
  - `by_feature`：GROUP BY feature → `[{"feature", "calls", "tokens", "usd"}]`，依 usd 降冪。
- `reset(conn) -> None`：`DELETE FROM usage_log`。

### 呼叫點插樁（每點抓 usage＋標 feature）

各 LLM 函式加 `feature: str = ""` 參數；回應拿到後在**該 provider 私有函式內** `usage.record(feature, model, raw)`。
best-effort，不改既有回傳值與行為。

| 檔案:行 | 函式 | feature | usage 取法 |
|---|---|---|---|
| `llm.py` `_foundry_parse_json` | parse_json(foundry) | 呼叫端傳入 | `resp.usage`（record 後再解析 text） |
| `llm.py` `_openai_parse_json` | parse_json(openai) | 呼叫端傳入 | `resp.json()["usage"]` |
| `llm.py` `_foundry_chat_stream` | chat_stream(foundry) | 呼叫端傳入 | yield 完後 `stream.get_final_message().usage` |
| `llm.py` `_openai_chat_stream` | chat_stream(openai) | 呼叫端傳入 | 加 `stream_options={"include_usage": True}`；末個 `choices:[]` 的 chunk 帶 `usage`，捕獲後 record |
| `chat.py` `stream_with_tools` | 整理助手 | 常數 | 迴圈每輪 `final = stream.get_final_message()` 後 `record`（多輪各記一列） |
| `research.py` `_foundry_research` | 公司研究 | 常數 | `resp.usage` |
| `research.py` `_openai_research` | 公司研究 | 常數 | `resp.json()["usage"]` |
| `digest.py` `summarize` | 每日彙整 | 常數 | `resp.json()["usage"]` |

`feature` 由呼叫端傳入的三處（走 `llm.parse_json`）：
- `diagnosis.py:20` → `feature="履歷健檢"`
- `match.py:23` → `feature="JD比對"`
- `tailor.py:31` → `feature="客製化"`
- `chat.py:266`（maybe_curate_memory）→ `feature="整理助手"`
- `chat.py:239`（maybe_compact，走 chat_stream）→ `feature="整理助手"`
- `web/app.py:48`（chat，走 chat_stream openai）→ `feature="整理助手"`

`llm.parse_json`/`chat_stream` 把 `feature` 往下傳給對應私有函式。`stream_with_tools`（web/app.py:46
的聊天）feature 固定 `"整理助手"`（函式內常數，不必呼叫端傳）。`research_company` 加 `feature` 參數
預設 `"公司研究"` 傳給私有函式。`digest.summarize` 內部固定 `"每日彙整"`。

**涵蓋所有 LLM 出口**——數字才不會誤導。

### 端點（`web/app.py`）

- `GET /api/usage` → `usage.summary(conn)`（讀本地 DB，無瀏覽器、無 LLM；不會 409/502）。
- `DELETE /api/usage` → `usage.reset(conn)` → `{"status": "reset"}`。

## 前端

### `api.ts`
- `UsageSummary` 介面：`{ total_tokens, total_usd, by_feature: UsageFeature[] }`；
  `UsageFeature`：`{ feature, calls, tokens, usd }`。
- `getUsage(): Promise<UsageSummary>`；`resetUsage(): Promise<Response>`。

### 側欄左下角（`Sidebar.tsx`）
- 側欄底部（導覽清單下方）常駐一小塊 `UsageBadge`：
  - TanStack Query `useQuery(["usage"], getUsage, { refetchInterval: 30000 })`。
  - 顯示：`◔ {tokens 精簡}  ${usd}`——tokens 用 `k`/`M` 精簡（如 `12.3k`）、usd 顯示 4 位小數
    （如 `$0.0123`）；小字、次要色，符合 Cockpit 深色主題。
  - 點擊 → 開 Mantle `Modal`「Token 用量」：
    - 上方總計（總 token、總 USD）。
    - `Table`：功能／次數／token／USD（by_feature，已依 usd 降冪）。
    - 「歸零」按鈕（red，`Modal` 內二次確認或直接呼叫）→ `resetUsage()` → invalidate `["usage"]`。
  - 讀取中/失敗：badge 顯示占位（`—`），不阻塞側欄。

## 邊界與安全

- 記帳 **best-effort、不阻塞、不改既有行為**：`usage.record` 全程 try/except，任何例外都不得
  往上冒到 LLM 呼叫。定價不準是已知（`_PRICING` 可調；Foundry 計費可能不同）。
- `GET /api/usage`/`DELETE` 純本地 DB 操作，不碰瀏覽器、不送 LLM、無 PII。
- 不做（YAGNI）：今日/本月分段、跨裝置同步、匯出、每次呼叫時間序圖、per-model 明細分頁。

## 測試

- `usage.cost_of`：已知 token 數 × 已知單價 → 驗算出的 USD（含 cache read/write）。
- `usage._price_for`：sonnet 命中 sonnet 筆、未知模型回 default。
- `usage.normalize`：
  - Anthropic 物件（含 cache_creation/cache_read）→ 正確四欄。
  - OpenAI dict（含 `prompt_tokens_details.cached_tokens`）→ input 扣掉 cached、cache_read=cached。
  - OpenAI dict 無 cache 欄 → cache 皆 0。
  - raw=None → 全 0 不炸。
- `usage.record`+`summary`+`reset` round-trip（用臨時 DB）：記數列 → summary 的 total/by_feature
  正確且依 usd 降冪 → reset 後清空。
- `usage.record` best-effort：normalize 丟例外時 record 不往上拋（monkeypatch normalize 拋例外，
  斷言 record 不 raise）。
- 插樁點：以假 client（回帶 usage 的假 resp）驗 `parse_json(feature=…)` 後 `usage.record` 被呼叫、
  feature 與 model 正確（monkeypatch `usage.record` 收參數）；驗既有回傳值不變（LLM 行為零回歸）。
- 端點：`GET /api/usage`（monkeypatch summary）結構、`DELETE /api/usage` 呼叫 reset。
- 前端 build 零 TS 錯誤。
- 真機：跑幾個功能（健檢/比對/聊天）→ 側欄左下角 token/USD 增加 → 點開看逐功能明細 → 歸零歸零。
