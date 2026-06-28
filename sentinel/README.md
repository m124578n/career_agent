# career-sentinel — 104 地端哨兵

地端、單人、自帶 key 的求職助手。Playwright（rebrowser-patches 反偵測版）驅動專用
Chrome profile（不存帳密），讀 104 登入後的「誰看過我 / 投遞狀態 / 訊息」，存 SQLite
快照、跟上次比對變化、LLM 彙整。104 私人頁在 Cloudflare 後面，故用打過 patch 的驅動以
自動通過 challenge。

## 安裝
    cd sentinel
    uv sync
    uv run rebrowser_playwright install chromium   # 裝 patch 過的瀏覽器驅動

## 使用
    cp .env.example .env   # 填 LLM key
    uv run career-sentinel login   # 首次：開 Chrome 手動登入 104
    uv run career-sentinel run     # 平常：擷取 → 比對 → 彙整
