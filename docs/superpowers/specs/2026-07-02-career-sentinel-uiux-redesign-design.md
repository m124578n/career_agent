# career-sentinel UI/UX 整體改版設計（SP-UIUX）

> 日期：2026-07-02。狀態：使用者已核可設計（視覺方向與版面經 visual companion mockup 確認），待出 plan。
> 前情：SP1–SP8 完成、191 測試綠。前端目前為 Mantine 7 深色**預設主題**（零客製）＋頂部 Tabs 六分頁。

## 目標

「要設計感、介面簡單」——整體視覺升級為 **Cockpit 色系 × Exaggerated Minimalism 版面**
（使用者從三個 mockup 方向中選定的混合方案），導覽從頂部 Tabs 改為**左側欄**，
六個分頁一次全部重整。**純前端改版：後端 API、資料流、業務邏輯零變動。**

## 視覺系統（新 `sentinel/web/frontend/src/theme.ts`）

### 色彩（自雲端 `frontend/src/theme.ts` 移植，值逐字複製）
- `ink`（覆寫 Mantine `dark` 色階）：`#e8e6e3`(0 文字) `#c6c3c6` `#a3a0a6`(muted) `#969399`(dim)
  `#302d34`(邊框) `#262329` `#201f24`(面板) `#15151a`(bg) `#101013` `#0a0a0c`
- `tangerine`（primary、shade 5 = `#ff6a3d`）：唯一「行動」色——主按鈕、★關注、active 強調
- `teal`（shade 5 = `#34d6c8`）：正向訊號——分數、面試時間、+N 增量
- `amber`（shade 5 = `#e9a23b`）：警示——邀約標記、提醒橫幅
- `danger`（shade 6 = `#e85d5d`）：錯誤
- 完整 10 階色值以雲端 `frontend/src/theme.ts` 為準（plan 內逐字複製）。深色 only，不做淺色模式。

### 字體（Google Fonts 於 `index.html` 引入）
- 標題／KPI 數字：**Space Grotesk**（500/700）
- 內文：**IBM Plex Sans**（400/600）
- 數字、時間、代碼：**IBM Plex Mono**（500）

### 版面原則（Exaggerated Minimalism）
1. **大字級 KPI**：Space Grotesk 700、48–56px、`letter-spacing: -2~-3px`、下方小型 letter-spaced 標籤
2. **去邊框扁平面板**：清單列／卡片用 `#1c1b20` 色塊＋`radius 8px`，不再用 `withBorder`
3. **留白加大**：頁面 padding 32px+、區塊間距 `xl`
4. **行動色稀缺性**：每頁只有一顆 tangerine 實心主按鈕；次要動作用 outline/subtle
5. **Icon 全面 SVG**：新增 `@tabler/icons-react`；替換現有 emoji icon
   （🧠→IconBrain、🧹→IconEraser、✕→IconX、★→IconStar、側欄六項各配 icon）。
   徽章文案內的 emoji 一併移除、改 icon＋文字。

## AppShell 側欄（取代頂部 Tabs）

- Mantine `AppShell`：`navbar` 寬 200px 固定（不做收合、不做 RWD 漢堡——本地桌面工具）
- 側欄內容（上→下）：
  1. 字標 `SENTINEL_`（Space Grotesk 700、tangerine 底線游標點綴）
  2. 六個 `NavLink`：儀表板/履歷健檢/JD 比對/推薦/職缺搜尋/整理助手（Tabler icon＋label、
     active 膠囊底 `#232128`）
  3. 底部（`margin-top:auto`）：**全域「重新抓取」按鈕**（tangerine，從 Dashboard 移出，
     跨頁可按、沿用既有 scrape/status 輪詢邏輯）＋上次抓取時間（Plex Mono 小字）
- **SP6 到點提醒橫幅**移到內容區頂部全域顯示（App 層，不再只在儀表板）；
  Web Notification 授權請求邏輯不變
- 分頁切換狀態管理沿用現有 `useState`（tab → active page key）；ChatPage 維持 keepMounted 等效
  行為（切頁不卸載——AppShell 下用條件 `display:none` 或沿用 Tabs.Panel keepMounted 機制，
  plan 擇一，需保住「切頁不丟聊天狀態」）

## 六頁重整（版面重排，資料流不動）

| 頁 | 重點 |
|---|---|
| 儀表板 | 大字級 KPI 列（誰看過我+N／即將面試／新訊息+邀約標記）→ 即將到來的面試 → 三清單（扁平列、hover 高亮、時間右對齊 Plex Mono）→ 今日彙整（純文字區）。「重新抓取」移側欄後，頁內不再有主按鈕 |
| 履歷健檢 | 統一頁首（標題＋一句副標）；上傳/職稱/薪資表單收斂為一個扁平面板；診斷結果雙欄（優勢 teal／待補強 amber）|
| JD 比對 | 頁首＋單一輸入列＋結果面板（分數大字級 teal、reasons/gaps 條列）|
| 推薦 | 頁首＋「拉取推薦」（頁內主按鈕）＋JobRow 清單 |
| 職缺搜尋 | 頁首＋搜尋輸入（Enter 觸發不變）＋JobRow 清單 |
| 整理助手 | 氣泡配色對齊：user 氣泡 `#232128`、助手氣泡無底色靠排版區隔；建議卡片/🧠徽章改 icon＋新色；memory 側欄融入右欄扁平面板 |

共用 `JobRow` 元件同步新視覺（★關注 tangerine IconStar、薪資 teal、比對按鈕 subtle）。

## UX 檢查表（隨頁落實，ui-ux-pro-max 規則）

- 所有可點元素 `cursor-pointer`＋hover 視覺回饋（色彩/底色過渡 150–300ms，不用會位移的 scale）
- 鍵盤 focus ring 可見（Mantine 預設保留、不得關閉）
- loading 既有邏輯保留（按鈕 loading、串流鎖輸入）
- 文字對比 ≥ 4.5:1（ink 色階已滿足：#e8e6e3 on #15151a）
- 動畫尊重 `prefers-reduced-motion`（Mantine 內建）

## 不做（YAGNI）

- 淺色模式、RWD 行動版（本地桌面工具）
- 側欄收合、多視窗、自訂主題切換
- 任何後端/API 變更、任何業務邏輯變更

## 測試與驗證

- 純前端：`npm run build` 零 TS 錯誤＝每任務關卡；後端 191 測試應全程不動且保持綠
  （merge 前跑一次確認零後端 diff 影響）
- 真機目視驗收：六頁逐頁看（版面/配色/字體/側欄導覽/全域重新抓取/提醒橫幅/聊天切頁不丟狀態）

## 設計依據

- 視覺方向、導覽結構、定案長相皆經 visual companion mockup 由使用者選定
  （C 混合方向、B 左側欄；session 檔案在 `.superpowers/brainstorm/`，gitignored）
- 色彩/字體來源：雲端 `frontend/src/theme.ts`（Cockpit 主題）；版面語彙：ui-ux-pro-max
  「Exaggerated Minimalism」＋ dashboard 資料密度指引
