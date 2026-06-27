# 設計規格：首頁（公開 Landing + 登入後 Dashboard）

- 日期：2026-06-27
- 範圍：前端新增首頁（公開 landing 與登入後總覽 dashboard）
- 狀態：設計已確認，待寫實作計畫

## 背景與目標

`career_agent` 前端（job-tracker）目前沒有真正的首頁：`/` 直接 `Navigate` 到
`/resume`，未登入時顯示 `LoginScreen`。本案新增首頁，採「**聚焦漏斗**」方向：

- **公開 Landing（轉換）**：未登入訪客 10 秒看懂「這工具幫我做什麼」並願意登入。
- **登入後 Dashboard（定向）**：回訪者一眼知道「我在哪、下一步做什麼」，以
  「履歷→職缺→追蹤」旅程為主軸。

沿用既有「溫暖指揮艙」設計語言與 token，不改後端/API/業務邏輯。

非目標（Out of scope）：
- 不做多段式行銷站（特色/FAQ/見證等）——日後可再擴充。
- 不改既有 `/resume`、`/jobs`、`/applications`、`/about` 的內部行為。
- 不新增後端端點；dashboard 只用既有 API。

## 路由與進入模型

| 路徑 | 存取 | 行為 |
|---|---|---|
| `/` | 公開（決策頁 `Home`） | 未登入 → 顯示 `Landing`；已登入 → `Navigate` 到 `/home` |
| `/home` | 需登入（側欄 shell 內） | `Dashboard` 總覽 |
| `/resume` `/jobs` `/applications` | 需登入 | 不變 |
| `/about` | 公開 | 不變 |

- `Home` 決策元件用 `useAuth()`：`enabled && !token` → `Landing`；否則
  `<Navigate to="/home" replace/>`。當登入 disabled（無需登入）時亦導向 `/home`。
- **登入成功 → 進 `/home`**（取代現行直接到 `/resume`）。Landing 的登入沿用既有
  `useAuth().login()`；token 落定後 `/` 決策頁自動帶到 `/home`。
- 側欄（`App.tsx` 的 `GatedLayout`）新增導覽項「**總覽**」（編號 `00`，→ `/home`），
  置於現有 01–04 之前；品牌 logo 連到 `/home`。
- 既有 `AuthGate` 行為不變（未登入深連 `/resume` 等仍顯示 `LoginScreen`）。

## Landing（公開、約一屏、轉換導向）

版面（深色 cockpit，沿用 `.jt-panel` / teal / tangerine / 既有網格暈光背景）：

- **頂列**：品牌 `JobTracker.` + 右側「關於作者 →」連 `/about`。
- **Hero**：大標（Space Grotesk）「AI 求職指揮艙」+ 一句價值主張「從履歷到 offer，
  一站幫你搞定」+ 單一主 CTA「用 Google 登入，開始」（tangerine）+ 可信度小字
  「由 詹舜智打造 · 每日免費額度」（連 `/about`）。
- **能力小卡 ×4**：履歷診斷 / 職缺契合度 / 求職信生成 / 投遞追蹤；每張 icon + 標題 +
  一行說明（沿用 `frontend/src/components/icons.tsx` 既有圖示，不足則用既有風格補）。
- **Footer**：沿用 `Footer` 元件。
- 等寬字只用於數字/標籤；小標與內文一般字體（沿用基底規則）。

## Dashboard（登入後 `/home`，引導下一步）

版面（在側欄 shell 內，`maw` 約 1180、置中）：

- **歡迎列**：「歡迎回來 👋」+ 精簡狀態（今日額度 `used/limit`、追蹤中 `N`）。
- **你的下一步**（核心引導大卡）：依狀態顯示一句行動 + 一顆 CTA。
- **求職旅程**：三步軌道 ①履歷與目標 →②職缺契合度 →③追蹤清單，高亮目前所在步，
  各步顯示簡短狀態（已完成 / 進行中 / N 筆），點擊可前往各頁。

### 「下一步」狀態機（產品核心邏輯）

依序判斷，命中即為當前下一步：

1. 無履歷/目標（`useResume().target` 為空）→「先設定履歷與目標」→ `/resume`
2. 有履歷、無搜尋紀錄（`api.listSearches()` 為空）→「去找契合的職缺」→ `/jobs`
3. 有搜尋、尚無追蹤（`api.listApplications()` 為空）→「把有興趣的職缺加入追蹤」→ `/jobs`
4. 已有追蹤 →「管理你的追蹤清單」→ `/applications`

資料來源（皆既有）：`useResume`（履歷/目標，需在 `ResumeProvider` 內——`/home`
置於 `GatedShell` 下即具備）、`api.listSearches`、`api.listApplications`、`api.quota`。
查詢失敗或載入中：以中性狀態呈現（例如下一步預設為步驟 1、狀態列顯示 `—`），不阻斷頁面。

## 程式落點

- 新增：
  - `frontend/src/pages/Landing.tsx`（公開、全屏、含 Google 登入 CTA）
  - `frontend/src/pages/Dashboard.tsx`（gated，旅程引導 + 狀態列）
  - `frontend/src/pages/Home.tsx`（`/` 決策：Landing 或導向 /home）
- 修改：
  - `frontend/src/main.tsx`：路由調整（`/` → `Home`；新增 gated `/home` → `Dashboard`；
    `Landing`/`Dashboard` 以 `lazy` 載入，與既有頁一致）。
  - `frontend/src/App.tsx`：`GatedLayout` 側欄 `NAV` 加「總覽」（→ `/home`）、品牌連 `/home`。
- 沿用：溫暖指揮艙 token、`Footer`、`icons.tsx`、`EmptyState`（如需）。

## 無障礙

- 維持對比 ≥ 4.5:1、`:focus-visible`、`prefers-reduced-motion`。
- 旅程軌道與 CTA 可鍵盤操作；裝飾性圓點 `aria-hidden`。

## 驗證計畫

- `cd frontend && npm run build` 通過。
- 跑起 `npm run dev` 目視：
  - 未登入到 `/` 看到 Landing；點登入後進 `/home`。
  - `/home` 四種狀態的「下一步」正確（無履歷 / 有履歷無搜尋 / 有搜尋無追蹤 / 有追蹤）。
  - 側欄「總覽」與品牌連結可達 `/home`；既有頁未受影響。
- 抽查 AA 對比；回歸確認 `/`→`/resume` 舊跳轉移除後無死連結。
