# 追蹤清單：面試筆記 + Offer 記錄

日期：2026-06-23
狀態：設計定稿，待實作

## 目標

讓使用者在「追蹤清單」中，針對每筆職缺記錄面試過程（時間軸筆記），並在拿到
offer 時記下 offer 細節；當有多筆 offer 時可並排比較（compete offer）。

## 背景與現況

追蹤清單目前是 5 欄看板（待投遞／已投遞／面試中／Offer／結束），每張卡片只有
職缺標題、公司、狀態下拉、移除。

資料模型已有基礎：

- `ApplicationEvent(ts, type, note)` 與 `Application.events: list[...]` 已存在
- `set_status` 切換狀態時，已自動 push 一筆 `type="status"` 的 event
- 但前端完全沒把 events 顯示出來，也沒有寫筆記的入口

因此本功能大半是「把既有 events 接到前端 + 補自由筆記入口 + 新增 offer 細節」。

## 設計決策（已與使用者確認）

1. 筆記形態：**時間軸 + 自由筆記**（非結構化面試輪次）。
2. Offer：**單筆為主**，多筆時提供 **compare/compete** 視圖。
3. 詳情 UI：**右側 Drawer 滑出**（看板不動，空間夠放時間軸與 offer）。
4. 薪資欄：**自由文字**（可寫「月 60k＋年終 2 個月」），compare 並排目視比較，
   不做自動排序。
5. Offer 表單：**只在狀態為 `offer` 時出現**，保持 Drawer 乾淨。

## 資料模型（backend schema）

新增 `OfferInfo`，全欄位 optional：

```python
class OfferInfo(BaseModel):
    salary: str | None = None      # 自由文字，如「月 60k＋年終 2 個月」
    level: str | None = None       # 職等 / title
    start_date: str | None = None  # 到職日（自由文字或 YYYY-MM-DD）
    accepted: bool | None = None   # 是否接受
    note: str | None = None        # 補充
```

`Application` 新增欄位：

```python
offer: OfferInfo | None = None
```

時間軸沿用既有 `events`：
- 狀態變更：`type="status"`，note 形如 `→ offer`（既有行為，不變）
- 自由筆記：`type="note"`，note 為使用者輸入文字（新增）

## 後端 API（applications router）

新增兩支端點（皆需登入、不耗 LLM 額度，沿用既有風格）：

- `POST /applications/{job_id}/notes`
  - body：`{ "note": str }`
  - 行為：push 一筆 `ApplicationEvent(type="note", note=...)`，更新 `updated_at`
  - 回傳：更新後的 `Application`
- `PATCH /applications/{job_id}/offer`
  - body：OfferInfo（部分欄位）
  - 行為：set `offer`，更新 `updated_at`
  - 回傳：更新後的 `Application`

`list_applications` 既有回傳已含 `events`，加上新欄位 `offer` 後前端一次拿齊，
不需額外 API。Repository 對應新增 `add_note` 與 `set_offer` 方法。

## 前端

### 看板卡片（AppCard）

- 多兩個輕量 hint：`💬 n`（筆記 event 數）、有 offer 時顯示 `💰`
- 整張卡片可點 → 開右側 Drawer
- 既有的狀態下拉與移除 ✕ 保留

### 詳情 Drawer

由上到下：

1. 職缺標題 / 公司（連結到原職缺）
2. 狀態下拉（沿用現有 Select 邏輯）
3. **Offer 區**：僅當 `status === "offer"` 顯示。表單欄位：薪資 / 職等 / 到職日 /
   是否接受 / 備註；變更後打 `PATCH /offer`
4. **時間軸**：events 倒序列出，`status` 與 `note` 兩種 event 用不同樣式區分；
   底部一個輸入框「+ 加筆記」，送出打 `POST /notes`

### Offer 比較（compare）

- 當看板上 **≥2 筆** `status === "offer"`，「Offer」欄頂端出現「比較」按鈕
- 點開 Modal，把這些 offer 並排成表格（公司 / 薪資 / 職等 / 到職日 / 備註）
- 純呈現，無排序、無計算

## API client / types（前端）

- `types`：`Application` 加 `offer?: OfferInfo`；新增 `OfferInfo`、`ApplicationEvent` 型別
- `client`：新增 `addApplicationNote(jobId, note)`、`setApplicationOffer(jobId, offer)`
- 所有 mutation 成功後 `invalidateQueries(["applications"])`

## 刻意不做（YAGNI）

- 不做全域統計數字看板（單筆記 + compare 已滿足）
- 不做結構化面試輪次（已選自由筆記）
- 不做薪資自動排序 / 幣別換算

## 測試

- 後端：`add_note` 後 events 多一筆且 type/note 正確；`set_offer` 後 offer 欄位
  正確；對不存在的 job_id 回 404
- 前端：型別檢查通過；Drawer 開關、加筆記後時間軸更新、offer 表單僅 offer 狀態
  顯示、≥2 筆 offer 時比較按鈕出現
