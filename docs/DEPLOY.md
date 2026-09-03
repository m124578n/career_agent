# 部署指南

架構：**前端 Cloudflare Pages** + **後端 Google Cloud Run（Docker，asia-east1）** + **DB MongoDB Atlas**。

> 2026-09：後端已從 Zeabur 搬到 Cloud Run（Zeabur 資安事件後棄用，API key 已輪替）。

> 串接順序重要：先部署後端拿到網址 → 再設前端的 API 網址 + 後端的 CORS 白名單。

---

## 0. 前置

### MongoDB Atlas（已完成）
- 連線字串放在後端環境變數 `MONGO_URI`。
- ⚠️ **Network Access**：Cloud Run 出口 IP 是動態的，白名單要用 `0.0.0.0/0` + 強密碼（要鎖 IP 得另外設 VPC connector + 固定 NAT，單人專案不值得）。

### Google OAuth Client ID（登入用）
1. Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID → **Web application**。
2. **Authorized JavaScript origins** 填前端網址：`http://localhost:5173`（dev）+ 你的 Cloudflare 網址（prod）。
3. 拿到的 **Client ID** 兩邊都要填：後端 `GOOGLE_CLIENT_ID`、前端 `VITE_GOOGLE_CLIENT_ID`（同一個值）。
4. 後端 `GOOGLE_CLIENT_ID` **留空 = 停用登入**（本機開發方便）；正式環境一定要填。
5. `DAILY_CALL_LIMIT` 控制每人每日 LLM 呼叫上限（預設 50）。

---

## 1. 後端 → Google Cloud Run

- GCP 專案：`tokyo-skein-415808`（OAuth client 也在這個專案）、region `asia-east1`（台灣）。
- 服務名 `job-tracker-api`，現行正式網址：`https://job-tracker-api-637238770294.asia-east1.run.app`。
- **部署是手動跑 gcloud**（不是 push 觸發）。從 repo 根目錄：

```bash
gcloud run deploy job-tracker-api --source backend --region asia-east1 \
  --allow-unauthenticated --memory 512Mi
```

`--source backend` 會用 Cloud Build 吃 `backend/Dockerfile` 建 image（純 httpx，無 Playwright）。
環境變數會沿用上一版，不用每次帶；要改時用 `--update-env-vars KEY=VALUE`，或整包用
`--env-vars-file env.yaml`（機密別進 git）。需要的變數：

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

`PORT` 由 Cloud Run 自動帶入（8080），Dockerfile 已處理。scale-to-zero，閒置不計費、冷啟動數秒。

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
   | `VITE_API_BASE_URL` | 後端網址 + `/api`：`https://job-tracker-api-637238770294.asia-east1.run.app/api` |
   | `VITE_GOOGLE_CLIENT_ID` | 與後端 `GOOGLE_CLIENT_ID` 同一個 |

4. SPA 路由已用 `frontend/public/_redirects` 處理（所有路徑 → index.html）。
5. 部署後記下前端網址，例：`https://career-agent-at2.pages.dev`。
6. **自訂網域**（現行正式網址 `https://jobtracker.shunzz.com`）：Pages → Custom domains 加網域，Cloudflare DNS 會自動加 CNAME；狀態從 initializing 轉 active 約 1–2 分鐘。加完後**必做**下面「回填 CORS」與「Google OAuth」兩步。

---

## 3. 回填 CORS（讓前端能打後端）

改 Cloud Run 的 `ALLOWED_ORIGINS`，填前端正式網址（可逗號分隔多個，**結尾不帶 `/`**）：

```bash
gcloud run services update job-tracker-api --region asia-east1 \
  --update-env-vars "ALLOWED_ORIGINS=https://jobtracker.shunzz.com,https://career-agent-at2.pages.dev"
```

更新即生效（會自動切新 revision）。驗證（應回 200，且帶 `access-control-allow-origin`）：

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X OPTIONS \
  https://job-tracker-api-637238770294.asia-east1.run.app/api/health \
  -H "Origin: https://jobtracker.shunzz.com" -H "Access-Control-Request-Method: GET"
```

## 4. Google OAuth 加新 origin

換／加前端網域時，Google Cloud Console → APIs & Services → Credentials → 該 OAuth Client：

- **Authorized JavaScript origins** 加 `https://jobtracker.shunzz.com`
- （本專案用 GIS token 流程，不需 redirect URI；若有設也一併加）

沒加會出現 `origin_mismatch` / 登入按鈕 403。Google 端生效可能延遲數分鐘。

---

## 日後版更（已上線後）

- **前端**：push `main` 自動觸發 Cloudflare Pages rebuild。
- **後端**：**手動跑 `gcloud run deploy`**（Cloud Run 沒接 repo，push 不會動後端）。

> **分支慣例**：日常開發在 `dev` 分支，驗證 OK 才合併進 `main`。push `dev` 時 Cloudflare 給 preview URL。

### 一般版更（改程式碼）

```bash
# 1. 改完先在本機自我驗證（部署前必做，別拿線上 build 當測試）
cd frontend && npm run build       # 前端能 build
cd ../backend && uv run pytest -q  # 後端測試全綠

# 2. commit + push 到 main（觸發前端部署）
git add -A && git commit -m "..."
git push origin main

# 3. 後端有改的話，另外部署
gcloud run deploy job-tracker-api --source backend --region asia-east1
```

上線後快速驗證：

```bash
curl -s https://job-tracker-api-637238770294.asia-east1.run.app/health       # 後端活著
curl -s -o /dev/null -w "%{http_code}" https://jobtracker.shunzz.com/        # 前端 200
```

再開網站實際登入 + 跑一次診斷確認。

### 例外：不是 push 就能生效的情況

| 情況 | 怎麼做 |
|------|--------|
| 只改**後端環境變數**（API key、CORS、額度…） | `gcloud run services update job-tracker-api --region asia-east1 --update-env-vars KEY=VALUE`，**push 沒用** |
| **加新環境變數**（程式碼會讀新 env） | 先設好變數（後端 gcloud / 前端 Cloudflare dashboard），再 push code，避免上線讀到空值 |
| 加**新前端 `VITE_` 變數** | Cloudflare 設好變數後**要重新 build**（Vite 是 build 時注入，非 runtime）|
| 改錯要回滾 | 前端：Cloudflare dashboard 點舊部署 Rollback。後端：`gcloud run services update-traffic job-tracker-api --region asia-east1 --to-revisions <舊revision>=100` |

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
