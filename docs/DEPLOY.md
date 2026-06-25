# 部署指南

架構：**前端 Cloudflare Pages** + **後端 Zeabur（Docker）** + **DB MongoDB Atlas**。

> 串接順序重要：先部署後端拿到網址 → 再設前端的 API 網址 + 後端的 CORS 白名單。

---

## 0. 前置

### MongoDB Atlas（已完成）
- 連線字串放在後端環境變數 `MONGO_URI`。
- ⚠️ **Network Access**：把後端平台（Zeabur）的出口 IP 加白名單；不確定 IP 就先用 `0.0.0.0/0` + 強密碼。

### Google OAuth Client ID（登入用）
1. Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID → **Web application**。
2. **Authorized JavaScript origins** 填前端網址：`http://localhost:5173`（dev）+ 你的 Cloudflare 網址（prod）。
3. 拿到的 **Client ID** 兩邊都要填：後端 `GOOGLE_CLIENT_ID`、前端 `VITE_GOOGLE_CLIENT_ID`（同一個值）。
4. 後端 `GOOGLE_CLIENT_ID` **留空 = 停用登入**（本機開發方便）；正式環境一定要填。
5. `DAILY_CALL_LIMIT` 控制每人每日 LLM 呼叫上限（預設 50）。

---

## 1. 後端 → Zeabur

1. Zeabur 建立 Service，連到此 repo。
2. **Root Directory 設成 `backend`**（monorepo，Dockerfile 在 `backend/`）。
3. Zeabur 會用 `backend/Dockerfile` build（純 httpx，無 Playwright，image ~510MB）。
4. 設定環境變數（Variables）：

   | 變數 | 值 |
   |------|----|
   | `MONGO_URI` | Atlas 連線字串 |
   | `MONGO_DB` | `job_tracker` |
   | `LLM_PROVIDER` | `foundry` |
   | `FOUNDRY_API_KEY` | Azure Foundry key |
   | `FOUNDRY_BASE_URL` | `https://<resource>.services.ai.azure.com/anthropic` |
   | `FOUNDRY_MODEL` | `claude-sonnet-4-6` |
   | `ALLOWED_ORIGINS` | 前端正式網址（部署完前端後回填，見步驟 3） |
   | `GOOGLE_CLIENT_ID` | Google OAuth Client ID（登入用） |
   | `DAILY_CALL_LIMIT` | `50`（每人每日 LLM 呼叫上限） |
   | `ADMIN_EMAILS` | 你的 email（可看全站 token 用量，逗號分隔多個） |
   | `LOG_LEVEL` | `INFO` |
   | `AGENT_SECRET` | 本機爬蟲 agent 的共享密鑰（與 `agent/.env` 相同；空 = 停用 agent 端點） |

5. `PORT` 由 Zeabur 自動帶入，Dockerfile 已處理。
6. 部署後記下後端網址，例：`https://career-agent-api.zeabur.app`。

---

## 2. 前端 → Cloudflare Pages

1. Cloudflare Pages 連到此 repo。
2. 設定：
   - **Root directory**：`frontend`
   - **Build command**：`npm run build`
   - **Build output directory**：`dist`
3. 環境變數：

   | 變數 | 值 |
   |------|----|
   | `VITE_API_BASE_URL` | 後端網址 + `/api`，例：`https://career-agent-api.zeabur.app/api` |
   | `VITE_GOOGLE_CLIENT_ID` | 與後端 `GOOGLE_CLIENT_ID` 同一個 |

4. SPA 路由已用 `frontend/public/_redirects` 處理（所有路徑 → index.html）。
5. 部署後記下前端網址，例：`https://career-agent.pages.dev`。

---

## 3. 回填 CORS（讓前端能打後端）

回到 Zeabur 後端的 `ALLOWED_ORIGINS`，填前端正式網址（可逗號分隔多個）：

```
ALLOWED_ORIGINS=https://career-agent.pages.dev
```

重新部署後端即生效。

---

## 本機爬蟲 Agent（104 封 IP 對策）

104 網站封鎖機房 IP（防爬），故爬職缺必須用住宅 IP。解方：在開發機（家裡）跑一個小 agent，定期輪詢後端任務隊列、爬取資料、回傳結果。

### 運作原理

- **後端** enqueue 爬蟲任務到 MongoDB（非同步）。
- **Agent**（開發機）每隔一段時間呼叫 `/api/agent/claim`，拉出待爬任務。
- **Agent** 以住宅 IP 連 104，抓職缺資訊，POST `/api/agent/callback` 回傳結果。
- Agent 離線時，任務會排隊；Agent 上線後自動執行。

### 設定步驟

1. **後端（Zeabur）設定 `AGENT_SECRET`**

   在 Zeabur dashboard 的環境變數加一行：
   ```
   AGENT_SECRET=<隨便一個複雜密鑰，例：$(openssl rand -base64 24)>
   ```
   重新部署後端。

2. **本機 Agent 設定**

   在開發機的 `agent/.env` 填：
   ```
   AGENT_SECRET=<與後端相同的密鑰>
   CLOUD_BASE_URL=https://career-agent-api.zeabur.app
   ```

3. **啟動 Agent**

   ```bash
   cd agent
   uv sync        # 安裝依賴
   uv run python agent.py
   ```

   Agent 會持續執行，每次輪詢都印出 log。

### 注意事項

- **Agent 要一直開著**（如要爬職缺）；建議用 `tmux` 或後台執行（如 `nohup`）。
- **`AGENT_SECRET` 留空 = 停用 agent 端點**，Agent 無法連接。
- **換密鑰務必同時改** Zeabur 和 `agent/.env`，否則認證失敗。
- 爬蟲失敗（如 104 IP 變化、網站異動）會記在 MongoDB，檢查後端 log 診斷。

---

## 日後版更（已上線後）

部署採 **push `main` 自動觸發**：Zeabur 接 `backend/`、Cloudflare Pages 接 `frontend/`。

> **分支慣例**：日常開發在 `dev` 分支，驗證 OK 才合併進 `main`。只有 `main` 會觸發正式部署；push `dev` 不動後端，Cloudflare 則給 preview URL。

### 一般版更（改程式碼）

```bash
# 1. 改完先在本機自我驗證（部署前必做，別拿線上 build 當測試）
cd frontend && npm run build       # 前端能 build
cd ../backend && uv run pytest -q  # 後端測試全綠

# 2. commit + push 到 main
git add -A && git commit -m "..."
git push origin main
```

push 後兩邊各自自動 rebuild 部署，在 dashboard 看 build log。上線後快速驗證：

```bash
curl -s https://career-agent.zeabur.app/health                              # 後端活著
curl -s -o /dev/null -w "%{http_code}" https://career-agent-at2.pages.dev/  # 前端 200
```

再開網站實際登入 + 跑一次診斷確認。

### 例外：不是 push 就能生效的情況

| 情況 | 怎麼做 |
|------|--------|
| 只改**環境變數**（API key、CORS、額度…） | 在 **Zeabur / Cloudflare dashboard** 改 + 重新部署，**push 沒用** |
| **加新環境變數**（程式碼會讀新 env） | 先在 dashboard 設好變數，再 push code，避免上線讀到空值 |
| 加**新前端 `VITE_` 變數** | Cloudflare 設好變數後**要重新 build**（Vite 是 build 時注入，非 runtime）|
| 改錯要回滾 | 兩平台都留部署歷史，dashboard 點舊版本 **Rollback** |

### 踩雷紀錄

- **CORS preflight 噴 400**：`ALLOWED_ORIGINS` **結尾不可帶 `/`**。瀏覽器送的 Origin 永遠不帶斜線，逐字比對才會過（例：`https://career-agent-at2.pages.dev`，不是 `.../`）。
- 重大改動可先開 branch / PR，Cloudflare 會給 preview URL 先看，沒問題再合 `main`。

---

## 本地開發（對照）

- 後端：`cd backend && uv run uvicorn job_tracker.main:app --reload`（讀 `backend/.env`）
- 前端：`cd frontend && npm run dev`（`VITE_API_BASE_URL` 留空 → 走 Vite proxy `/api` → localhost:8000）
- DB：`docker compose up -d`（本機 Mongo）或直接連 Atlas

---

## 驗證清單

- [ ] 後端 `GET /health` 回 `{"status":"ok"}`
- [ ] 前端載入，側欄顯示，能切換頁面（SPA 路由 OK）
- [ ] 上傳履歷 → 診斷成功（代表前端能打後端 + CORS OK + LLM 正常）
- [ ] 側欄 token 用量有跳動（代表 Atlas 寫入 OK）
