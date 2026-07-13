# 線上版 admin 營運數據 dashboard — 設計

**日期**：2026-07-13
**範圍**：線上多人版（`backend/` FastAPI+MongoDB / `frontend/` React）。新增 admin-only 營運數據頁。
**部署注意**：merge 到 `main` 會自動部署（Cloudflare Pages 前端 + Zeabur 後端）。

## 目標

給站長（admin）一頁只有他看得到的營運數據：使用人數、活躍度、用量成本、每日活躍趨勢。從既有資料聚合，不新增事件追蹤。

## 資料現況

MongoDB collections（皆帶 `user`＝Google email）：`jobs`、`matches`（status: candidate/pending/done/failed）、`searches`（`user`, `created_at`, `keyword`, `count`）、`daily_usage`（`_id="{user}|{day}"`, `user`, `day`, `count`）、`token_usage`（`TokenUsageRepository.summary()` 已聚合 token/成本）、`applications`（`user`）。admin 判定：`auth.is_admin(user)`（`ADMIN_EMAILS`，逗號分隔）；`/usage/global` 已 admin-gated。無專門 users/analytics collection。

## 使用者決定（已確認）

- 範圍＝**匯總數字 + 每日趨勢**；不做個人明細表、不加事件追蹤。

## 架構

### ① 聚合服務 `backend/src/job_tracker/services/admin_stats.py`

`async def compute_admin_stats(db) -> AdminStats`，用既有 collection 聚合：

- `total_users`：`daily_usage` 的 distinct `user` 數（曾消耗額度＝真實用過的人）。
- `active_7d` / `active_30d`：`daily_usage` 中 `day >= 今天(UTC)−6 / −29`（含今天，共 7/30 天窗）的 distinct `user` 數。`day` 格式沿用既有寫入（見 QuotaRepository，字串日期 YYYY-MM-DD 字典序可比較）。
- `total_searches`：`searches` 文件數。
- `total_analyzed`：`matches` 中 `status == "done"` 的文件數。
- `total_applications`：`applications` 文件數。
- `tokens` / `llm_calls`：取自 `TokenUsageRepository.summary(user=None)`（回 `{calls, input_tokens, output_tokens, total_tokens, by_model}`）——`tokens=total_tokens`、`llm_calls=calls`。（該 summary 不含成本 USD，故 v1 不呈現成本。）
- `daily_active`：`list[{day, users}]`，近 30 天每日 distinct user 數。以 `daily_usage` aggregate：`$group {_id: "$day", users: {$addToSet: "$user"}}` → `{day, users: size}`，篩 `day >= 今天−29`、依 `day` 升冪。缺席的日子在服務層補 0（回傳連續 30 天，前端不用補洞）。

`AdminStats`（Pydantic，放 `schemas`）：
```python
class DailyActive(BaseModel):
    day: str
    users: int

class AdminStats(BaseModel):
    total_users: int = 0
    active_7d: int = 0
    active_30d: int = 0
    total_searches: int = 0
    total_analyzed: int = 0
    total_applications: int = 0
    tokens: int = 0
    llm_calls: int = 0
    daily_active: list[DailyActive] = []
```

聚合以 Motor 的 `distinct`/`count_documents`/`aggregate`。壞資料/空 collection → 對應欄位 0／空列，不拋錯。

### ② API 端點

於既有 `api/routers/usage.py` 加 `GET /usage/admin-stats`：`current_user` 依賴 + `if not is_admin(user): 403`；回 `(await compute_admin_stats(db)).model_dump()`。需注入 db（依既有 deps 模式取得 Motor db handle）。唯讀。

### ③ 前端

- `frontend/src/api/client.ts`：`adminStats()` → `GET /usage/admin-stats`，型別 `AdminStats`（對齊後端）。
- `frontend/src/pages/AdminStats.tsx`（新）：TanStack Query 打 `adminStats`；stat 磚（總人數 / 7天活躍 / 30天活躍 / 總搜尋 / 總分析 / 總投遞 / tokens / LLM 呼叫次數）+ 近 30 天每日活躍水平長條（純 CSS/既有元件，**不加圖表套件**）。
- 路由與導覽：`/admin` 路由；nav 項與頁面**僅在 `quota.is_admin` 為真時**顯示/可達（沿用 `App.tsx` 既有的 `quota` query 與 `AccountFooter` 判 admin 的模式）。非 admin 直接進 `/admin` → 顯示「僅管理者可檢視」提示（後端 403 為真正防線）。
- 載入 `Loader`、錯誤 `Alert`、無資料友善占位。

## 資料流

AdminStats 頁 →（admin-gated）`GET /usage/admin-stats` → usage router 檢查 `is_admin` → `compute_admin_stats(db)` 聚合既有 collection → `AdminStats` JSON → 前端渲染。

## 錯誤處理

- 非 admin → 後端 403、前端顯示提示。
- 空/新站（無資料）→ 全 0、`daily_active` 為連續 30 天皆 0，不拋錯。
- 日期以 UTC 計（與 `daily_usage.day` 寫入一致）。

## 測試

- `backend/tests`：`compute_admin_stats` 對種入的 `daily_usage`/`searches`/`matches`/`applications`/`token_usage` 聚合正確——distinct user 計數、7/30 天活躍窗邊界、`total_analyzed` 只計 done、`daily_active` 連續 30 天且缺日補 0。端點：admin → 200 + shape、非 admin → 403。（沿用既有後端測試的 DB fixture 方式。）
- 前端：`npm run build`。

## 非目標（YAGNI）

- 不做個人明細（per-user）表。
- 不加事件追蹤（登入/頁面瀏覽/留存曲線）。
- 不做即時、不做匯出。
- 留言板／意見回饋為**另一個獨立功能**，另案設計。
