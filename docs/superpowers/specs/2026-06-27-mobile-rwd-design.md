# 設計規格：手機 RWD 針對性修補

- 日期：2026-06-27
- 範圍：前端（job-tracker SPA）手機響應式修補
- 狀態：設計已確認，待寫實作計畫

## 背景與目標

`career_agent` 前端在桌機已套用「溫暖指揮艙」設計，且具備基本 RWD 基礎：
App shell 已有手機 burger + 收合側欄（`App.tsx`），各頁 padding/標題字級已用
`{ base, md }` 響應式，控制列多處已 `wrap="wrap"`。

但仍有數處桌面式版面在手機上難用。本案採「**針對性修補**」：只修真正會壞/難用
的點，不為手機從零重做版面、不逐頁全面打磨。**不動任何後端 / API / 業務邏輯，
桌機版面維持不變。**

非目標（Out of scope）：
- 不做手機優先的全頁重設計，不逐元件微調間距/字級。
- 不改後端、API、資料流、既有 mutation/query 行為。
- 不改桌機（≥sm）版面與互動。
- 不處理平板專屬版面（沿用桌機版，斷點以 sm 為界）。

## 統一斷點

- 以 Mantine `sm`（768px / 48em）作為手機↔桌機唯一分界，與側欄收合斷點一致。
- 需要 JS 分流之處用 `useMediaQuery("(max-width: 48em)")`（`@mantine/hooks`，
  專案已使用）。SSR 不適用（純 CSR Vite SPA），`useMediaQuery` 初值預設 `false`
  （即先當桌機）可接受；不需額外防閃爍處理。
- 純樣式分流優先用 Mantine 既有響應式 props（`hiddenFrom`/`visibleFrom`、
  `{ base, sm }` 物件語法），只有元件結構需切換時才用 `useMediaQuery`。

## 修補項目

### 1. 追蹤清單看板（`frontend/src/pages/Applications.tsx`）

桌機（≥sm）：維持現狀——5 欄 `Group wrap="nowrap"` 橫向看板，欄內
`maxHeight: calc(100vh - 280px)` 獨立捲動。

手機（<sm）：
- 在搜尋框下方加一條狀態切換器（`SegmentedControl`），5 個選項對應
  `COLUMNS`，標籤含該狀態筆數（例「待投遞 2」）。預設選第一個（`to_apply`）。
- 一次只顯示被選狀態的那一欄：卡片（`AppCard`）垂直排列，**移除欄內
  `maxHeight` + `overflowY` 獨立捲動**，改由整頁自然捲動（消除巢狀捲動）。
- 空狀態維持「還沒有」文案。
- `AppCard`、`AppDrawer`、`CompareButton` 元件邏輯不變，只調呈現容器。
- 狀態切換器的選中值用 `useState`，初值 `COLUMNS[0].status`。

實作方式：以 `useMediaQuery` 取 `isMobile`，在 render 時：
`isMobile` → 渲染 `SegmentedControl` + 單欄卡片清單；否則渲染現有 5 欄 `Group`。
兩條路徑共用同一份 `visible`（關鍵字篩選結果）與 `AppCard`。

### 2. Modal / Drawer 手機全螢幕

窄螢幕下對話框不再擠壓或溢出：

- 求職信 Modal（`JobList.tsx` `MatchCard` 內，現 `size="lg"`）→ 手機
  `fullScreen`。
- Offer 比較 Modal（`Applications.tsx` `CompareButton` 內，現 `size="lg"`）→
  手機 `fullScreen`。
- Offer 編輯 Drawer（`Applications.tsx` `AppDrawer`，現 `position="right"
  size="md"`）→ 手機 `size="100%"`（桌機維持 `"md"`）。

實作：各元件用 `useMediaQuery` 取 `isMobile`；Modal 加
`fullScreen={isMobile}`，Drawer 用 `size={isMobile ? "100%" : "md"}`。
其餘 props（title、closeOnClickOutside 等）不變。

### 3. Offer 比較表（`Applications.tsx` `CompareButton`）

現為裸 `Table`，5 欄在窄螢幕會撐破 Modal。改用 Mantine
`Table.ScrollContainer`（`minWidth` 設一合理值，例 480）包住 `Table`，
讓表格自身可橫向捲動而不撐破容器。桌機外觀不受影響。

### 4. JobList 候選列（`frontend/src/pages/JobList.tsx`，候選 `candidates.map`）

現為單行 `Group wrap="nowrap"`：checkbox、標題（`flex:1`）、公司、薪資、
（廣告？chip）。窄螢幕標題被壓扁。

改為：checkbox 維持在左（`align="flex-start"`），右側改為一個垂直區塊——
第一行職稱（`jt-job-title`），第二行公司 · 薪資 · 標籤（`Group gap wrap="wrap"`，
`fz="xs" c="dimmed"`）。桌機與手機共用此結構（兩行式在桌機也成立、更清楚），
不需 `useMediaQuery` 分流。確保長字串以 `truncate` 或自然換行不溢出。

### 5. 點擊目標（觸控友善）

手機上屬「主要動作」且目前 `size="xs"` 的按鈕，於 <sm 放大到 `sm`，用
`size={{ base: "sm", sm: "xs" }}` 物件語法（Mantine Button 支援）或
`useMediaQuery` 視情況：
- 候選面板：「分析選中」「爬下一頁」（`JobList.tsx`）。
- 看板分頁切換器（項目 1 的 `SegmentedControl`，手機本就主要動作，size 用 `sm`）。

次要/密集按鈕（收合、重試、chip 內按鈕）維持 `xs`，避免版面破壞。
checkbox 不改尺寸，但其所在列（候選列、全選列）行高/`gap` 已足夠點擊。
ActionIcon（移除、刪除搜尋）現為 `size="lg"`，點擊區足夠，不動。

### 6. 防溢出收尾

手動在 375px 寬逐頁確認無水平捲動溢出；長公司名 / 薪資字串以既有
`truncate` 或換行處理。標題字級已是響應式，不動。Landing / Dashboard /
ResumeSetup / About 既已大量使用響應式 props，僅在收尾目視時順手確認，
無預期改動。

## 程式落點

- 修改：
  - `frontend/src/pages/Applications.tsx`（看板手機分頁、Modal/Drawer 全螢幕、
    比較表 ScrollContainer、比較按鈕觸控尺寸）。
  - `frontend/src/pages/JobList.tsx`（求職信 Modal 全螢幕、候選列兩行式、
    主要按鈕觸控尺寸）。
- 沿用：`@mantine/hooks` 的 `useMediaQuery`、Mantine 響應式 props、既有
  `.jt-*` token 與元件，無新增 CSS class（如需極少量樣式，加到 `global.css`）。
- 不改：`App.tsx`（shell 已具手機支援）、`theme.ts`、後端、API client、
  state（auth/resume）、其他頁面邏輯。

## 無障礙

- `SegmentedControl` 本身可鍵盤操作；確保選項有可辨識標籤。
- 維持既有對比 ≥4.5:1、`:focus-visible`、`prefers-reduced-motion` 規則，不移除。
- 全螢幕 Modal/Drawer 維持既有 close 控制與 focus trap（Mantine 預設）。

## 驗證計畫

- `cd frontend && npm run build`（`tsc -b && vite build`）通過——本專案無單元
  測試框架，build 即驗證閘門。
- 手動在約 375px 寬（手機）目視：
  - 追蹤清單：狀態分頁切換正常、單欄垂直捲動、無巢狀捲動；桌機仍 5 欄。
  - 求職信 / Offer 比較 / Offer 編輯在手機為全螢幕、不溢出；比較表可橫捲。
  - JobList 候選列兩行式不被壓扁；主要按鈕點擊區舒適。
  - 全頁無水平溢出。
- 桌機（≥sm）回歸目視：各頁版面與互動與修補前一致。
