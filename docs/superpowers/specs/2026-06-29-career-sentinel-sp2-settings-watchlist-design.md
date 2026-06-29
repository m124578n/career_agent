# 設計規格：career-sentinel SP2 — 設定 + 關注清單

- 日期：2026-06-29
- 範圍：`sentinel/`；在 SP1 web app 上加設定頁（關注公司/職缺關鍵字/通知時間）+ 儀表板即時標記
- 狀態：設計已確認，待寫實作計畫
- 路線圖：[../career-sentinel-roadmap.md](../career-sentinel-roadmap.md)（SP2）

## 背景與目標

SP1 完成了本地 web 儀表板（`career-sentinel serve`：三面板 + 彙整 + 重新抓取）。
使用者想設定「想收到訊息的時間」與「關注的公司/職缺關鍵字」，並讓系統定期檢視符合條件者。

SP2 做這套設定的**地基**：一個設定頁讓使用者編輯並持久化三項設定，並讓**關注清單在儀表板上立刻有可見效果**
（命中的公司/關鍵字項目標記「關注」）。通知時間本輪**只存不發**（SP6 才真正按時通知）；
關注用於**推薦過濾**在 SP5。

成功定義：在儀表板開「設定」可編輯關注公司/關鍵字/通知時間並存下（重開仍在）；
儀表板上符合關注條件的 viewer/應徵/訊息項目顯示「★ 關注」標記。

### 非目標（Out of scope，留後續 SP）

- 按通知時間實際發通知（SP6）；用關注過濾推薦（SP5）。
- 多組通知時間 / 進階排程；關注的更複雜比對（正則、排除字）。
- 不改 Phase 1/2 既有抓取行為與 SP1 既有端點的回應「形狀」（snapshot 只**新增** `watched` 欄位）。

## 資料模型

`Settings`（Pydantic，放 `models.py`）：
```python
class Settings(BaseModel):
    watched_companies: list[str] = []
    watched_keywords: list[str] = []
    notify_time: str | None = None   # "HH:MM"，SP2 先存、SP6 才用
```

## 儲存（`store.py`）

單列 `settings` 表，以 JSON 存整個 Settings：
```sql
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT NOT NULL);
```
- `load_settings(conn) -> Settings`：讀 id=1 的 data；無則回 `Settings()`（預設空）。
- `save_settings(conn, settings: Settings)`：`INSERT OR REPLACE` id=1。
- 建表併入既有 `connect` 的 schema（與 snapshots 等一起建）。

## 關注比對（`watch.py`，純函式、可測、SP5 可重用）

```python
def is_watched(company: str, haystack: str, settings: Settings) -> bool:
    """命中任一關注公司（為 company 子字串、不分大小寫）或任一關鍵字（出現在 haystack）。"""
```
- 公司命中：任一 `watched_companies` 項（strip 後非空）以不分大小寫為 `company` 的子字串。
- 關鍵字命中：任一 `watched_keywords` 項（strip 後非空）以不分大小寫出現在 `haystack`。
- 空白項（strip 後為空）忽略；兩清單皆空 → 一律 False。

各面板的 haystack：viewer=`job_title`、application=`title`、message=`last_message`。

## API（FastAPI，接 SP1 `web/app.py`）

- `GET /api/settings` → Settings JSON。
- `PUT /api/settings`（body=Settings）→ 驗證後存，回存後的 Settings。
  - 驗證 `notify_time`：None 或符合 `^([01]\d|2[0-3]):[0-5]\d$`；不合 → 422。
- `GET /api/snapshot` 擴充：載入 settings，對每個 item 算 `watched: bool` 一併回傳
  （viewers/applications/messages 各 item 多 `watched` 欄位；其餘欄位與 SP1 相同）。
  - 用 `create_app` 的 `resolved_db` 載 settings（與 snapshot 同一 DB）。

## 前端（接 SP1 儀表板）

- 頂部「設定」按鈕 → Mantine **Modal**：
  - 關注公司（Textarea，一行一個）、職缺關鍵字（Textarea，一行一個）、通知時間（`<input type="time">` 或 Mantine TimeInput）。
  - 開啟時 `GET /api/settings` 帶入；存 → `PUT /api/settings` → 成功後關閉並 `invalidateQueries(["snapshot"])`（讓標記刷新）。
- 三面板 item：`watched` 為 true 時顯示「★ 關注」徽章。
- 用 TanStack Query 管 settings 查詢。

## 錯誤處理

- `PUT /api/settings` 壞 `notify_time` → 422，前端顯示「時間格式需為 HH:MM」。
- 設定表不存在 → `connect` 建表時一併建；`load_settings` 無資料回預設。
- 後端仍只綁 127.0.0.1。

## 測試

- **`is_watched`** 純函式：公司子字串命中、關鍵字命中、不分大小寫、空白項忽略、空設定→False。
- **store**：`save_settings`/`load_settings` round-trip；無設定 → 預設 `Settings()`。
- **API**（TestClient + 暫時 SQLite）：GET 預設、PUT round-trip、PUT 壞 notify_time → 422、
  snapshot 帶 `watched`（存一筆命中關注公司的快照 + 設定 → 該 item `watched=true`）。
- **前端**：`npm run build` 通過 + 人工目視（設定存得起來、徽章出現）。
- Phase 1/2/SP1 既有測試不得回歸。

## 開放問題（實作時釐清，不阻擋設計）

- 通知時間前端元件用原生 `<input type="time">` 或 Mantine `TimeInput`（`@mantine/dates`）——傾向原生，免加依賴。

## 後續

SP2 完成後接 SP3（履歷健檢）/SP4（JD 比對）/SP5（推薦，會用到本 SP 的關注比對）。見路線圖。
