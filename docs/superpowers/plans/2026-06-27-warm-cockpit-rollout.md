# 溫暖指揮艙 Rollout Implementation Plan（其餘頁面）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已確認的「溫暖指揮艙」設計基底與語言，套用到其餘所有前端表面（登入、追蹤清單、職缺契合度、關於我、側欄），並完成跨頁收尾（專用錯誤色、ink 對齊、殘留註解）。

**Architecture:** 設計基底（token、`EmptyState`、`ReadoutItem`）已於前一個 plan 落地並合併。本 plan 是逐表面套用：去除終端機符號（`//`、`[+]`/`[!]`）、口語化文案、友善空狀態、圓點 + 淡色襯底、色彩語意分流。先做一個跨頁基底收尾任務，再一頁頁推。

**Tech Stack:** React 18, Mantine 7, Vite 6, TypeScript 5。無單元測試框架——驗證 = `cd frontend && npm run build` 通過 + 視覺檢視。

## Global Constraints

- 只動前端呈現與文案；不改後端/API/資料流/業務邏輯。每個頁面既有的 mutations、queries、state、useEffect、事件處理必須完整保留。
- 色彩語意分流：tangerine `#ff6a3d` 只當主要行動；teal `#34d6c8` 正向/契合/連結；amber `#e9a23b`「可以加強」；**新增 danger `#ec6f6f`（色階 index 5）只當真正的錯誤/失敗**。
- 等寬字（IBM Plex Mono）只用於分數/數字/標籤值（如 nav 的 01–04、分數、token 數）；小標與內文用一般字體。
- 文案口語、鼓勵、給明確下一步；診斷/分析類先講亮點再講可加強。
- 去除終端機符號：移除文案中的 `//`、`[+]`、`[!]`、英文大寫技術標籤（READOUT/RANKED/CANDIDATES/ABOUT/SUPPORT…）。
- 重用既有元件：`EmptyState({title, description, action?})`、`ReadoutItem({kind:"pos"|"warn", children})`（在 `frontend/src/components/`）。
- 無障礙：文字/狀態色 ≥ 4.5:1；保留 `:focus-visible`、`aria-label`、`prefers-reduced-motion`。
- 設計原則：資料保持精準，對人說話保持溫暖。
- 指令在 `frontend/` 執行；Bash 工具為 Git Bash。
- 已確認決策：(1) 錯誤色用專用 danger 柔紅；(2) 職缺分數配定性詞；(3) theme.ts 的 ink 對齊成暖化值。

---

### Task 1: 跨頁基底收尾（danger 色 + ink 對齊 + 殘留註解）

**Files:**
- Modify: `frontend/src/theme.ts`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Produces: Mantine 色 `danger`（`c="danger.5"` 可用）；CSS 變數 `--jt-danger`；theme.ts `dark`(ink) 色階對齊 `--jt-*` 暖化值。後續任務的錯誤文字一律用 `c="danger.5"`。

- [ ] **Step 1: theme.ts 新增 danger 色階並對齊 ink**

在 `frontend/src/theme.ts` 的 `amber` 之後、`ink` 之前新增：

```ts
const danger: MantineColorsTuple = [
  "#fff0f0", "#ffe0e0", "#fbc4c4", "#f5a3a3", "#f08585",
  "#ec6f6f", "#e85d5d", "#cf4848", "#b83b3b", "#9e2e2e",
];
```

把 `ink` 色階整個替換為對齊 `--jt-*` 的暖化值：

```ts
const ink: MantineColorsTuple = [
  "#e8e6e3", // 0 主要文字（= --jt-text）
  "#c6c3c6", // 1
  "#a3a0a6", // 2 muted（= --jt-muted）
  "#969399", // 3 dim（= --jt-dim）
  "#302d34", // 4 邊框（= --jt-border）
  "#262329", // 5 面板2（= --jt-panel-2）
  "#201f24", // 6 面板（= --jt-panel）
  "#15151a", // 7 body 背景（= --jt-bg）
  "#101013", // 8
  "#0a0a0c", // 9
];
```

把 `colors` 改為加入 danger：

```ts
  colors: { tangerine, teal, amber, danger, dark: ink },
```

- [ ] **Step 2: global.css 新增 --jt-danger 並修正殘留註解**

在 `frontend/src/styles/global.css` 的 `:root` 中，於 `--jt-amber` 那行之後新增一行：

```css
  --jt-danger: #ec6f6f; /* 真正的錯誤/失敗（與行動色 tangerine 分離）*/
```

找到 `.jt-readout` 上方的殘留註解（仍寫著 `[+] 優勢 / [!] 待補強`），替換為：

```css
/* 診斷項目清單容器（項目見 .jt-item，標記見 .jt-dot）*/
```

- [ ] **Step 3: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 成功。注意 ink 變更會影響 Mantine 內部深色面板（Select/Modal/Drawer 等），這是預期的「一起變暖」。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/theme.ts frontend/src/styles/global.css
git commit -m "feat(fe): rollout 基底收尾（danger 柔紅、ink 對齊暖化值、修殘留註解）"
```

---

### Task 2: 登入頁 LoginScreen

**Files:**
- Modify: `frontend/src/components/LoginScreen.tsx`

**Interfaces:**
- Consumes: 既有 `.jt-panel`（已暖化）、`.jt-brand`、`.jt-brandtag`。

- [ ] **Step 1: 暖化登入卡的文案與層次**

把 `LoginScreen.tsx` 中內層 `.jt-panel` 卡片內容（從 `<span className="jt-brand"...>` 到該 `<div>` 結束、`GoogleLogin` 之前）替換為：

```tsx
          <span className="jt-brand" style={{ fontSize: 22 }}>
            JobTracker<span className="dot">.</span>
          </span>
          <div className="jt-brandtag" style={{ marginTop: 8 }}>
            AI 求職指揮艙
          </div>
          <p style={{ color: "var(--jt-text)", fontSize: 16, fontWeight: 600, margin: "22px 0 6px" }}>
            準備好開始找下一份工作了嗎？
          </p>
          <p style={{ color: "var(--jt-muted)", fontSize: 14, margin: "0 0 20px", lineHeight: 1.6 }}>
            用 Google 登入，我陪你做履歷診斷、找契合的職缺、寫求職信。
            <br />
            每日有免費使用額度。
          </p>
```

（`GoogleLogin` 區塊與其餘不變。）

- [ ] **Step 2: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LoginScreen.tsx
git commit -m "feat(fe): 登入頁暖化文案（歡迎語、口語價值說明）"
```

---

### Task 3: 追蹤清單 Applications

**Files:**
- Modify: `frontend/src/pages/Applications.tsx`

**Interfaces:**
- Consumes: 既有 `.jt-panel`、`.jt-jobcard`、`.jt-eyebrow`（已 sans）。

- [ ] **Step 1: 頁首說明口語化**

把第 42 行的說明 `Text`：

```tsx
        <Text c="dimmed" fz="sm">把職缺加入後，在這裡管理投遞與面試進度。</Text>
```

替換為：

```tsx
        <Text c="dimmed" fz="sm">把有興趣的職缺加進來，在這裡追蹤投遞與面試進度。</Text>
```

- [ ] **Step 2: 看板欄位空狀態友善化**

把欄位內容中的空狀態（約第 70–74 行）：

```tsx
                  {items.length === 0 ? (
                    <Text fz="xs" c="dimmed">—</Text>
                  ) : (
```

替換為：

```tsx
                  {items.length === 0 ? (
                    <Text fz="xs" c="dimmed" ta="center" py={8}>還沒有</Text>
                  ) : (
```

- [ ] **Step 3: Drawer 內標籤去大寫感、時間軸空狀態友善化**

把 Drawer 內 `OFFER` 標籤（約第 194 行）：

```tsx
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>OFFER</div>
```

替換為：

```tsx
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>Offer 內容</div>
```

把時間軸區塊的空狀態（約第 216–217 行）：

```tsx
            {events.length === 0 ? (
              <Text fz="xs" c="dimmed">—</Text>
```

替換為：

```tsx
            {events.length === 0 ? (
              <Text fz="xs" c="dimmed">還沒有紀錄，加一條筆記開始吧。</Text>
```

- [ ] **Step 4: Offer 比較 Modal 標題去大寫**

把 `CompareButton` 的 Modal 標題（約第 252 行）：

```tsx
             title={<span className="jt-eyebrow">OFFER 比較</span>}>
```

替換為：

```tsx
             title={<span className="jt-eyebrow">Offer 比較</span>}>
```

- [ ] **Step 5: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Applications.tsx
git commit -m "feat(fe): 追蹤清單暖化（友善空狀態、口語文案、去大寫標籤）"
```

---

### Task 4: 職缺契合度 JobList — 控制列 / 候選 / 結果 / 空狀態 / 文案

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`

**Interfaces:**
- Consumes: `EmptyState`（新 import）。
- Produces: 為 Task 5 保留 `MatchCard` 不變（Task 5 處理）。

- [ ] **Step 1: 新增 EmptyState import**

在 `JobList.tsx` 既有 import 區塊加入：

```tsx
import { EmptyState } from "../components/EmptyState";
```

- [ ] **Step 2: 「尚未設定履歷」空狀態改 EmptyState**

把 `!target` 分支的整個 `.jt-panel`（約第 180–191 行）替換為：

```tsx
        <div className="jt-panel">
          <div className="jt-panel-body" data-center="true">
            <EmptyState
              title="還沒設定履歷"
              description="先到「履歷與目標」上傳履歷、填好目標職位，再回來找契合的職缺。"
              action={
                <Button component={Link} to="/resume" color="tangerine" variant="light" size="sm">
                  去設定履歷 →
                </Button>
              }
            />
          </div>
        </div>
```

- [ ] **Step 3: 候選區與結果區的小標去終端機符號**

把候選區 `jt-panel-head` 的小標（約第 318 行）：

```tsx
                <span className="jt-eyebrow">候選 // CANDIDATES · {candidates.length}</span>
```

替換為：

```tsx
                <span className="jt-eyebrow">有興趣的候選 · {candidates.length}</span>
```

把結果區小標（約第 374–382 行）：

```tsx
              <span className="jt-eyebrow">
                分析結果 // RANKED
                {results.length ? (
                  <>
                    {" · "}
                    <b>{results.length}</b> 筆
                  </>
                ) : null}
              </span>
```

替換為：

```tsx
              <span className="jt-eyebrow">
                契合度排序
                {results.length ? (
                  <>
                    {" · "}
                    <b>{results.length}</b> 筆
                  </>
                ) : null}
              </span>
```

- [ ] **Step 4: 結果區空狀態改 EmptyState**

把結果區的空狀態（約第 428–432 行）：

```tsx
              ) : (
                <div className="jt-empty">
                  尚無結果 // 輸入關鍵字後執行「爬取候選」，勾選後「分析選中」
                </div>
              )}
```

替換為：

```tsx
              ) : (
                <EmptyState
                  title="還沒有分析結果"
                  description="先搜尋職缺、勾選有興趣的候選，再按「分析選中」，我幫你逐筆比對排序。"
                />
              )}
```

- [ ] **Step 5: 按鈕與爬取進度文案口語化**

把控制列的主按鈕（約第 216–224 行）文字 `爬取候選` 改為 `搜尋職缺`：

```tsx
                <Button
                  color="tangerine"
                  size="md"
                  disabled={!canRun}
                  loading={busy}
                  onClick={run}
                >
                  搜尋職缺
                </Button>
```

把爬取錯誤訊息（約第 232–236 行）：

```tsx
              {(createMut.isError || crawlMut.isError) && (
                <Text fz="xs" c="tangerine.5" mt={6}>
                  爬取失敗：請確認後端與關鍵字後再試。
                </Text>
              )}
```

替換為（改用 danger 色、口語）：

```tsx
              {(createMut.isError || crawlMut.isError) && (
                <Text fz="xs" c="danger.5" mt={6}>
                  搜尋沒成功，確認關鍵字或稍後再試一次。
                </Text>
              )}
```

把爬取進度 `AnalyzingSteps` 的步驟（約第 301–309 行）文字改口語：

```tsx
                <AnalyzingSteps
                  steps={[
                    "連線 104…",
                    "搜尋符合的職缺…",
                    "標記關鍵字命中…",
                    "整理候選清單…",
                  ]}
                  intervalSec={2}
                />
```

- [ ] **Step 6: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 成功（確認 `Link` 已 import——既有檔案頂部已 `import { Link } from "react-router-dom"`）。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(fe): 職缺頁暖化（友善空狀態、口語文案、danger 錯誤色、去終端符號）"
```

---

### Task 5: 職缺契合度 JobList — MatchCard（圓點/amber、分數定性、求職信 modal）

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`
- Modify: `frontend/src/styles/global.css`

**Interfaces:**
- Consumes: `ReadoutItem`（新 import）。

- [ ] **Step 1: 新增 ReadoutItem import 與分數定性 helper（含 tier）**

在 `JobList.tsx` import 區塊加入：

```tsx
import { ReadoutItem } from "../components/ReadoutItem";
```

在檔案中 `MatchCard` 函式定義之前，新增 helper（tier 同時驅動文字與顏色）：

```tsx
type FitTier = "high" | "mid" | "low";
function fitTier(score: number): FitTier {
  return score >= 80 ? "high" : score >= 60 ? "mid" : "low";
}
function fitLabel(tier: FitTier): string {
  return tier === "high" ? "很適合" : tier === "mid" ? "還不錯" : "可考慮";
}
```

- [ ] **Step 2: global.css 新增依契合度上色的定性詞樣式，並清除死 CSS**

在 `frontend/src/styles/global.css` 找到 `.jt-score b { ... }` 與 `.jt-score small { ... }` 區塊（約第 198–213 行），整段替換為（數字依 tier 上色 + 一般字體定性詞，移除舊 `small` 冷樣式）：

```css
.jt-score b {
  font-family: "IBM Plex Mono", monospace;
  font-size: 28px;
  font-weight: 600;
  line-height: 1;
  color: var(--jt-teal);
}
.jt-score b[data-fit="high"] { color: var(--jt-teal); }
.jt-score b[data-fit="mid"]  { color: var(--jt-amber); }
.jt-score b[data-fit="low"]  { color: var(--jt-dim); }
/* 定性詞：一般字體、依契合度上色（取代舊的 mono/大寫 small）*/
.jt-score .jt-fitlabel {
  display: block;
  font-family: "IBM Plex Sans", system-ui, sans-serif;
  font-size: 11px;
  font-weight: 600;
  margin-top: 4px;
}
.jt-score .jt-fitlabel[data-fit="high"] { color: var(--jt-teal); }
.jt-score .jt-fitlabel[data-fit="mid"]  { color: var(--jt-amber); }
.jt-score .jt-fitlabel[data-fit="low"]  { color: var(--jt-dim); }
```

接著清除已無人使用的死 CSS：刪掉整個 `.jt-tags { ... }` 規則、以及 `.jt-tag`、`.jt-tag .m`、`.jt-tag[data-kind="pos"] .m`、`.jt-tag[data-kind="neg"] .m` 這幾條規則（約第 230–252 行；MatchCard 已改用 `.jt-readout`/`ReadoutItem`，這些不再被引用）。

- [ ] **Step 3: 分數區塊配定性詞（依 tier 上色）**

把 `MatchCard` 內分數區塊（約第 501–504 行）：

```tsx
        <div className="jt-score">
          <b>{score}</b>
          <small>match</small>
        </div>
```

替換為：

```tsx
        <div className="jt-score">
          <b data-fit={fitTier(score)}>{score}</b>
          <span className="jt-fitlabel" data-fit={fitTier(score)}>{fitLabel(fitTier(score))}</span>
        </div>
```

- [ ] **Step 4: reasons/gaps 改用 ReadoutItem（圓點 + 淡色底，amber 取代 neg）**

把展開區的 `.jt-tags` 區塊（約第 523–536 行）：

```tsx
          <div className="jt-tags">
            {reasons.map((r, i) => (
              <div key={`r${i}`} className="jt-tag" data-kind="pos">
                <span className="m">[+]</span>
                <span>{r}</span>
              </div>
            ))}
            {gaps.map((g, i) => (
              <div key={`g${i}`} className="jt-tag" data-kind="neg">
                <span className="m">[!]</span>
                <span>{g}</span>
              </div>
            ))}
          </div>
```

替換為：

```tsx
          <div className="jt-readout">
            {reasons.map((r, i) => (
              <ReadoutItem key={`r${i}`} kind="pos">{r}</ReadoutItem>
            ))}
            {gaps.map((g, i) => (
              <ReadoutItem key={`g${i}`} kind="warn">{g}</ReadoutItem>
            ))}
          </div>
```

- [ ] **Step 5: 失敗狀態與求職信 modal 文案改 danger / 口語**

把結果清單中 `status === "failed"` 的卡片（約第 396–408 行）裡的 `分析失敗` 文案與重試保留，但把「分析失敗」狀態文字色調統一——將該卡片的 `.jt-job-meta` 內容：

```tsx
                            <div className="jt-job-meta">{m.job.company} · 分析失敗</div>
```

替換為：

```tsx
                            <div className="jt-job-meta">{m.job.company} · <span style={{ color: "var(--jt-danger)" }}>分析沒成功</span></div>
```

把求職信 Modal 的錯誤訊息（約第 595–598 行）：

```tsx
        ) : letterMut.isError ? (
          <Text fz="sm" c="tangerine.5">
            生成失敗，請重試。
          </Text>
```

替換為：

```tsx
        ) : letterMut.isError ? (
          <Text fz="sm" c="danger.5">
            生成沒成功，請再試一次。
          </Text>
```

- [ ] **Step 6: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 成功。確認移除 `.jt-tags`/`.jt-tag*` 後無其他檔案仍引用（MatchCard 已改用 `.jt-readout`/`ReadoutItem`）。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/JobList.tsx frontend/src/styles/global.css
git commit -m "feat(fe): MatchCard 暖化（分數定性詞+依契合度上色、圓點+amber、danger 錯誤色、清死 CSS）"
```

---

### Task 6: 關於我 About + 側欄 App.tsx 文案

**Files:**
- Modify: `frontend/src/pages/About.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: 既有 token 與 class。

- [ ] **Step 1: About 去終端機符號、coffee 按鈕用品牌色**

把 About 的小標 `關於我 // ABOUT`（約第 41 行）：

```tsx
              <span className="jt-eyebrow">關於我 // ABOUT</span>
```

替換為：

```tsx
              <span className="jt-eyebrow">關於我</span>
```

把 `支持我 // SUPPORT`（約第 79 行）：

```tsx
            <div className="jt-eyebrow" style={{ margin: "22px 0 8px" }}>支持我 // SUPPORT</div>
```

替換為：

```tsx
            <div className="jt-eyebrow" style={{ margin: "22px 0 8px" }}>支持我</div>
```

把咖啡按鈕的 `color="orange"`（約第 89 行）改為品牌主行動色：

```tsx
                color="tangerine"
```

- [ ] **Step 2: 側欄 quota 文案微調口語**

在 `frontend/src/App.tsx` 的 `AccountFooter`，把「今日額度」剩餘說明（約第 140–142 行）：

```tsx
        <div style={{ fontSize: 11, color: "var(--jt-dim)" }}>
          剩餘 {quota?.remaining ?? "—"} 次（每日重置）
        </div>
```

替換為：

```tsx
        <div style={{ fontSize: 11, color: "var(--jt-dim)" }}>
          還可用 {quota?.remaining ?? "—"} 次 · 每日重置
        </div>
```

- [ ] **Step 3: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/About.tsx frontend/src/App.tsx
git commit -m "feat(fe): 關於我與側欄暖化（去 // 標籤、品牌色按鈕、口語額度說明）"
```

---

### Task 7: 最終視覺 QA + 回歸（controller 自行執行）

**Files:** 無程式碼變更（必要微修回對應任務檔案）。

- [ ] **Step 1: 最終建置**

Run: `cd frontend && npm run build`
Expected: 成功。

- [ ] **Step 2: 跑起 dev 並逐頁目視**

`cd frontend && npm run dev`，逐一檢視：登入、履歷與目標、職缺契合度（含候選/結果/MatchCard 展開/求職信 modal）、追蹤清單（看板/Drawer/Offer 比較）、關於我、側欄。
重點：無殘留 `//`、`[+]`/`[!]`；錯誤訊息為柔紅 danger；分數有定性詞且依契合度上色（高 teal/中 amber/低 dim）；空狀態友善。
ink 對齊後**逐一確認這些 Mantine 內部元件**色調一致、邊界仍可辨、輸入框與面板不致糊在一起：TextInput / NumberInput / Textarea、Select（關閉與展開下拉）、MultiSelect、Modal、Drawer、Table（Offer 比較）、Badge（關於我技能）、Switch / Checkbox、Loader、Avatar。
AnalyzingSteps **刻意不改**（`✓`/`▸` mono 標記屬資料/進度語彙，符合副駕原則）——確認其在新 ink 下仍清楚即可。

- [ ] **Step 3: 無障礙抽查**

確認 danger `#ec6f6f`、amber、teal、dim 文字在各 panel 底上 ≥ AA。

- [ ] **Step 4: 回歸**

確認 ink 變更未造成任何頁面異常對比/不可讀；`.jt-tag` 雖保留但 JobList 已改用 `.jt-readout`（確認無視覺殘留衝突）。

- [ ] **Step 5: 最終 commit（若有微調）**

```bash
git add -A frontend/src
git commit -m "fix(fe): 溫暖指揮艙 rollout 視覺 QA 微調"
```

---

## 完成定義（rollout）

- 所有表面套用溫暖指揮艙語言：去終端符號、口語文案、友善空狀態、圓點 + 淡色底、色彩語意分流（含 danger 錯誤色）、分數定性詞。
- theme.ts ink 對齊暖化值（單一來源真正達成）。
- 每個任務 `npm run build` 通過；最終逐頁目視 + AA 抽查 + 回歸通過。
