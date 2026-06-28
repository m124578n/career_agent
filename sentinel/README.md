# career-sentinel — 104 地端哨兵

地端、單人、自帶 key 的求職助手。Playwright 驅動專用 Chrome profile（不存帳密），
讀 104 登入後的「誰看過我 / 投遞狀態 / 訊息」，存 SQLite 快照、跟上次比對變化、LLM 彙整。

## 安裝
    cd sentinel
    uv sync
    uv run playwright install chromium

## 使用
    cp .env.example .env   # 填 LLM key
    uv run career-sentinel login   # 首次：開 Chrome 手動登入 104
    uv run career-sentinel run     # 平常：擷取 → 比對 → 彙整
