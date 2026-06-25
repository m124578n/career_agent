# 本機爬蟲 agent

用家用住宅 IP 代打 104（雲端機房 IP 被 104 封）。輪詢雲端任務隊列 → 抓 104 → 回填原始 JSON。

先備好設定（兩種跑法都要）：`cp .env.example .env`，填 `CLOUD_BASE_URL` 與 `AGENT_SECRET`（與雲端 Zeabur 設定相同）。

## 跑法 A：Docker（推薦，乾淨好管理）

```bash
docker compose up -d --build   # 啟動（背景）
docker compose logs -f         # 看 log
docker compose down            # 停止
```

`restart: unless-stopped` → 崩潰自動重啟、開機自啟（Docker Desktop 有自啟時）。容器出口走主機網路，一樣是住宅 IP，104 不會擋。`.env` 只在執行期注入，不進 image。

## 跑法 B：直接跑

```bash
uv sync
uv run python agent.py
```

---

需要爬職缺時開著即可；關掉則任務在雲端排隊，下次開機自動跑完。
