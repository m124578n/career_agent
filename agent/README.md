# 本機爬蟲 agent

用家用住宅 IP 代打 104（雲端機房 IP 被 104 封）。輪詢雲端任務隊列 → 抓 104 → 回填原始 JSON。

## 跑法

1. `cp .env.example .env`，填 `CLOUD_BASE_URL` 與 `AGENT_SECRET`（與雲端設定相同）。
2. `uv sync`
3. `uv run python agent.py`

需要爬職缺時開著即可；關掉則任務在雲端排隊，下次開機自動跑完。
