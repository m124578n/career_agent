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
   | `LOG_LEVEL` | `INFO` |

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
