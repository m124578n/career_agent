# 線上版意見回饋（私密收件匣）— 設計

**日期**：2026-07-13
**範圍**：線上多人版（`backend/` FastAPI+MongoDB / `frontend/` React）。新增意見回饋：登入者送出、admin 私密收件匣。
**部署注意**：merge 到 `main` 會自動部署（Cloudflare Pages + Zeabur）。

## 目標

讓登入使用者送出意見回饋（建議／問題回報），進到只有站長（admin）看得到的收件匣；送出者看不到別人的回饋。

## 使用者決定（已確認）

- 私密（非公開）：任何登入者可送出；**只有 admin 能讀**。
- admin 收件匣放在既有 `/admin`（營運數據）頁下方一個新區塊。

## 資料現況（沿用）

MongoDB + Motor；repos 模式（每 collection 一個 Repository，`deps.get_X_repo`）；`auth.current_user`（Google email；dev 模式=dev@local）與 `auth.is_admin`（`ADMIN_EMAILS`）；端點在 `/api` 前綴；測試用 `mongomock_motor.AsyncMongoMockClient` + `app.dependency_overrides` + monkeypatch `is_admin`。既有 admin 頁 `AdminStats.tsx`（`/admin`，`quota.is_admin` gated）已在 dev。

## 架構

### ① 資料層

- 新 collection `feedback`，文件：
  ```
  _id: str (uuid)
  user: str          # 送出者 email（current_user）
  message: str       # 回饋內容
  category: str      # "建議" | "問題回報" | "其他"（預設 "其他"）
  created_at: str    # ISO（UTC）
  read: bool         # admin 已讀標記，預設 False
  ```
- `Feedback` schema（Pydantic，放 `schemas`；欄位同上，`read: bool = False`）。
- `FeedbackRepository`（`db/repositories.py`，`self._col = db["feedback"]`）：
  - `async def create(user: str, message: str, category: str) -> Feedback`：產生 uuid + `created_at=now(UTC).isoformat()` + `read=False`，insert，回 `Feedback`。
  - `async def list() -> list[Feedback]`：全部，依 `created_at` 由新到舊。
  - `async def mark_read(fid: str, read: bool) -> None`：更新 `read`。
  - `async def delete(fid: str) -> None`。
- `deps.get_feedback_repo() -> FeedbackRepository`。

### ② API（新 `api/routers/feedback.py`，掛在 `/feedback`）

- `POST /feedback`（任何登入者）：body `{message: str, category?: str}`。`message` strip 後為空 → 400；長度 > 2000 → 400；`category` 不在允許集合 → 用 "其他"。`repo.create(current_user, message, category)`；回 `{ok: True}`。
- `GET /feedback`（admin only）：非 admin → 403；回 `[Feedback...]`（新→舊）。
- `POST /feedback/{fid}/read`（admin only）：body `{read: bool}`；非 admin → 403；`repo.mark_read`；回 `{ok: True}`。
- `DELETE /feedback/{fid}`（admin only）：非 admin → 403；`repo.delete`；回 `{ok: True}`。
- 於 `api/routers/__init__.py` 註冊 feedback router。

### ③ 前端

- `api/client.ts`：`Feedback` 型別；`submitFeedback(message, category)`、`listFeedback()`、`markFeedbackRead(id, read)`、`deleteFeedback(id)`。
- **送出 UI**：`components/FeedbackButton.tsx`（新）——gated 版面（`App.tsx` 的側欄/AccountFooter 附近）放「意見回饋」按鈕 → Mantine `Modal`（`Textarea` + 類別 `Select`「建議／問題回報／其他」+ 送出）。送出成功關閉 + 通知（沿用既有 notifications 或簡單提示）；空內容禁止送出；錯誤顯示重試。所有登入者可見。
- **admin 收件匣**：在 `pages/AdminStats.tsx` 底部新增 `FeedbackInbox` 區塊（同頁 admin-gated；用 `useQuery(["feedback"], listFeedback, {enabled: is_admin})`）——列出回饋（新→舊）：email · 類別 · 時間 · 內容、已讀/未讀切換、刪除；未讀高亮（`jt-panel` 樣式）；操作後 `invalidateQueries(["feedback"])`。空清單顯示占位字。純 Mantine/CSS。

## 資料流

送出：FeedbackButton → `POST /api/feedback`（current_user）→ `FeedbackRepository.create` → feedback collection。
收件匣：AdminStats 頁 FeedbackInbox →（admin-gated）`GET /api/feedback` → repo.list → 前端列出；已讀/刪除 → `POST /feedback/{id}/read` / `DELETE /feedback/{id}`。

## 錯誤處理

- 未登入 → 端點依既有 `current_user` 行為（401）。空/過長訊息 → 400。非 admin 讀/改/刪 → 403。
- 前端送出/讀取錯誤 → 顯示提示 + 重試。

## 測試

- `backend/tests`：
  - `FeedbackRepository`：create 帶 user/category/read=False、list 新→舊排序、mark_read、delete。
  - 端點：`POST /feedback` 任何登入者 200 + 空訊息 400 + 過長 400；`GET /feedback` admin 200 / 非 admin（monkeypatch `is_admin`→False）403；`DELETE`、`read` admin 200 / 非 admin 403。用 `deps.get_feedback_repo` override mongomock。
- 前端：`npm run build`。

## 非目標（YAGNI）

- 不公開（只 admin 讀）、不做回覆串／email 通知／附件、不匿名。
- 不做分頁（v1 全列；量大再加）、不做垃圾訊息過濾（登入即可送、長度上限已擋）。
