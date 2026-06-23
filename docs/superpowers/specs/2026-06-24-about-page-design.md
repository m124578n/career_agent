# 關於我頁面 + 公開存取 + 全站 footer

日期：2026-06-24
狀態：設計定稿，待實作

## 目標

新增一個「關於我」頁面（名片式：自我介紹 + 聯繫方式），**登入前後都能看**（公開
路由），並在全站底部加上版權聲明（copyright footer）。

## 背景與現況

- 前端 `main.tsx`：`AuthGate` 包在 `BrowserRouter` **外**（gate 攔整個 app，
  router 在 gate 內），`AuthGate` 邏輯為 `enabled && !token → LoginScreen`。
- `App.tsx`：`AppShell` 側欄 + `NAV`（3 項，tag 01/02/03）+ 內部 `Routes`
  （/resume、/jobs、/applications）。
- 純前端、無後端參與。

## 設計決策（已與使用者確認）

1. `/about` **公開**（登入前後皆可訪問）+ 登入後也能從側欄進。
2. 聯繫方式 6 個渠道（見下）。
3. 名片式（非完整 portfolio）。
4. 自我介紹由我草擬、使用者可改；頭銜聚焦 Python Backend & AI Application。
5. 加全站 copyright footer。

## 1. 公開路由架構（`main.tsx` 重構）

把 `BrowserRouter` 提到 `AuthGate` 外，用 `Routes` 分流公開 vs 需登入：

```tsx
<AuthProvider>
  <BrowserRouter>
    <Routes>
      <Route path="/about" element={<About />} />        {/* 公開，無側欄 layout */}
      <Route path="/*" element={
        <AuthGate>
          <ResumeProvider>
            <App />
          </ResumeProvider>
        </AuthGate>
      } />
    </Routes>
  </BrowserRouter>
</AuthProvider>
```

- `About` 是公開頁，自己的置中 layout（不套 `AppShell` 側欄）。
- `App` 內現有的 `<Routes>`（/resume…）維持，巢狀在 `/*` 下匹配絕對路徑。
- `GoogleOAuthProvider` 與其餘 provider 結構不變。

## 2. About 頁（`pages/About.tsx`）

名片式、置中卡片、沿用 `jt-` 風格。由上到下：

- **名字 + 頭銜**：詹舜智 · Python Backend & AI Application Engineer
- **自我介紹**（草擬，使用者可改）：
  > 我是詹舜智，有 3.5 年 Python 後端開發經驗，專注於把 LLM 與 AI 應用整合進
  > 產品。曾在 Osense Technology 主導 AI 影片生成平台 OVideo，從零設計整條
  > pipeline、整合 GPT-4 / Claude / Gemini 等模型，並透過架構優化把營運成本
  > 減半、並發處理量擴展到 10 倍以上。熟悉 FastAPI 與 Django（曾在 iThome
  > 鐵人賽發表 30 篇 Django 原始碼解析），近期投入 RAG 檢索與地端 LLM 部署。
  > 我習慣把技術決策寫清楚、樂於分享，期待打造對使用者真正有用的 AI 產品。
- **技能標籤**（可選，使用者可增刪）：Python、FastAPI、Django、LLM 整合、
  Prompt Engineering、RAG、Docker、Azure
- **聯繫方式**（icon + 連結，逐項）：
  | 渠道 | 連結 |
  |---|---|
  | Email | `m23568n@gmail.com`（mailto） |
  | GitHub | `https://github.com/m124578n` |
  | LinkedIn | `https://www.linkedin.com/in/john19980215` |
  | Medium | `https://medium.com/@m23568n` |
  | dev.to | `https://dev.to/shunchih` |
  | 個人網站 | `https://m124578n.github.io/` |
- 頁底放 copyright footer（同第 4 節）。
- 公開頁可放一個小連結回首頁／登入（如「← 回 JobTracker」），讓訪客能進主站。

## 3. 側邊欄導航（`App.tsx`）

`NAV` 加一項：`{ to: "/about", label: "關於我", tag: "04" }`。登入後可從側欄進
`/about`（同一個公開頁元件）。

## 4. 全站 copyright footer

- 新元件 `components/Footer.tsx`：一行 `© 2026 詹舜智 · JobTracker`，
  字小、`--jt-dim` 色，可附 GitHub 連結。
- 放置三處：
  1. About 頁底。
  2. 登入頁 `LoginScreen` 底。
  3. app 側欄底（`App.tsx` 的 `AccountFooter` 下方）。

## 元件結構

- `pages/About.tsx` — 公開關於我頁（自包含 layout）。
- `components/Footer.tsx` — 版權列，三處共用。
- `main.tsx` — 路由重構（公開 vs gated 分流）。
- `App.tsx` — NAV 加項 + 側欄底 Footer。
- `components/LoginScreen.tsx` — 底部加 Footer。

## 刻意不做（YAGNI）

- 不做完整 portfolio（經歷/作品時間軸）。
- 不接後端、不存 DB（純靜態頁）。
- 不做 i18n、不做頭像上傳（要放頭像可後續加靜態圖）。
- copyright 年份先寫死 `2026`（要動態再說）。

## 測試 / 驗證

- 型別檢查 `tsc --noEmit` exit 0。
- 手動：未登入直接開 `/about` 可見（公開）；登入後從側欄「關於我」可進；六個
  聯繫連結正確、外部連結開新分頁；登入頁、app、about 三處都有 footer；其餘需登入
  路由仍被 gate 攔。

## 風險 / 注意

- **巢狀 Routes**：`App` 內的 `<Routes>` 在 `/*` 父路由下要維持絕對路徑匹配；實作
  時驗證 /resume、/jobs、/applications 仍正常（包含登入後直接開深層路徑）。
- 個人聯繫連結是公開資訊，放前端靜態頁無密鑰疑慮。
