# 溫暖指揮艙前端重新設計 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保留「指揮艙」品牌 DNA 的前提下，建立「溫暖指揮艙」共用設計基底，並套用到「履歷與目標」（ResumeSetup）示範頁，讓介面更親和、好上手。

**Architecture:** 先以 design token（`theme.ts` + `global.css`）建立單一來源的視覺基底（色彩語意分流、層次陰影、圓角、暖化）；再抽出兩個可重用 React 元件（EmptyState、ReadoutItem）承載新的元件與文案語言；最後在 ResumeSetup 套用全部並加入「下一步出口」。其餘頁面因共用 `--jt-*` 變數會「順便變溫暖」，完整改版另案逐頁進行。

**Tech Stack:** React 18, Mantine 7, Vite 6, TypeScript 5。無單元測試框架——驗證 = `npm run build` 通過 + 跑起 app 截圖檢視各狀態。

## Global Constraints

- 不改後端、API、資料流、業務邏輯；只動前端呈現與文案。
- 不更換元件庫；續用 Mantine + `theme.ts`。
- 色彩語意分流：`tangerine #ff6a3d` 只當主要行動；`teal #34d6c8` 當正向/契合/連結；新增 `amber #e9a23b`（index 5）當「可以加強的地方」。
- 等寬字（IBM Plex Mono）只用於分數/數字/標籤值；section 小標與說明文字用一般字體。
- 文案口語、鼓勵、給明確下一步；先講亮點再講可加強。
- 維持無障礙：文字/狀態色 ≥ 4.5:1、保留 `:focus-visible` 焦點環、icon 按鈕 `aria-label`、`prefers-reduced-motion` 關動畫。
- 設計原則：「像一位冷靜可靠的副駕」——資料保持精準，對人說話保持溫暖。
- 所有指令在 `frontend/` 目錄下執行（`cd frontend`）。

---

### Task 1: 設計基底 token（theme.ts + global.css）

**Files:**
- Modify: `frontend/src/theme.ts`
- Modify: `frontend/src/styles/global.css:1-12`（`:root` 變數區）與相關 class

**Interfaces:**
- Produces: CSS 變數 `--jt-amber`、`--jt-warn-bg`、`--jt-pos-bg`、`--jt-radius`、`--jt-radius-lg`、`--jt-shadow-1`、`--jt-shadow-2`、`--jt-panel-raised`；Mantine theme 新增 `amber` 色、`defaultRadius: "md"`。後續任務的卡片/標記/狀態色都引用這些。

- [ ] **Step 1: 在 theme.ts 新增 amber 色階並放大圓角**

於 `frontend/src/theme.ts`，在 `teal` 定義之後、`ink` 之前新增：

```ts
const amber: MantineColorsTuple = [
  "#fff8ec", "#fcedd2", "#f6d9a6", "#f1c576", "#ecb34f",
  "#e9a23b", "#d98f2a", "#b67322", "#925b1c", "#6f4413",
];
```

並把 `createTheme({...})` 改為：

```ts
export const theme = createTheme({
  fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', ui-monospace, monospace",
  headings: { fontFamily: "'Space Grotesk', system-ui, sans-serif" },
  primaryColor: "tangerine",
  primaryShade: 5,
  defaultRadius: "md", // 從 sm 放大：更舒服、更友善
  colors: { tangerine, teal, amber, dark: ink },
});
```

- [ ] **Step 2: 暖化 global.css 的 :root 變數並新增層次/狀態 token**

把 `frontend/src/styles/global.css` 開頭的 `:root { ... }`（第 1–12 行）整段替換為：

```css
:root {
  /* 呈現層單一來源：.jt-* 自訂 UI 一律用這些變數
     （theme.ts 的 dark 色階為求一致已對齊這裡的暖化值） */
  --jt-bg: #15151a;
  --jt-panel: #201f24; /* 由 #1e2127 微微加溫（偏暖中性） */
  --jt-panel-2: #262329;
  --jt-panel-raised: #2a272e; /* 浮起面板：比 panel 再亮一階 */
  --jt-border: #302d34; /* 邊框降對比、微帶暖 */
  --jt-text: #e8e6e3; /* 文字中性偏暖 */
  --jt-muted: #a3a0a6;
  /* 維持 ≥4.5:1 */
  --jt-dim: #8b8890;
  --jt-accent: #ff6a3d; /* tangerine：只當主要行動 */
  --jt-teal: #34d6c8; /* 正向 / 契合 / 連結 */
  --jt-amber: #e9a23b; /* 可以加強的地方（與行動色分離）*/

  /* 狀態淡色襯底 */
  --jt-pos-bg: rgba(52, 214, 200, 0.08);
  --jt-warn-bg: rgba(233, 162, 59, 0.1);

  /* 圓角 */
  --jt-radius: 12px;
  --jt-radius-lg: 16px;

  /* 層次：柔和陰影取代生硬 1px 線（搭配 border 一起用）*/
  --jt-shadow-1: 0 1px 2px rgba(0, 0, 0, 0.3);
  --jt-shadow-2: 0 6px 20px rgba(0, 0, 0, 0.35);
}
```

- [ ] **Step 3: 暖化共用面板/卡片並放大圓角**

在 `global.css` 找到 `.jt-panel` 規則（約第 40–47 行），改為：

```css
.jt-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--jt-panel);
  border: 1px solid var(--jt-border);
  border-radius: var(--jt-radius-lg);
  box-shadow: var(--jt-shadow-1);
}
```

- [ ] **Step 4: 柔化 .jt-eyebrow（小標改一般字體，去終端感）**

在 `global.css` 找到 `.jt-eyebrow`（約第 26–33 行），改為一般字體、降字距、不再小寫轉大寫；
保留 `.jt-eyebrow b` 的 teal 強調：

```css
/* 小標：一般字體、克制字距（等寬字只留數字/標籤值）*/
.jt-eyebrow {
  font-family: "Space Grotesk", system-ui, sans-serif;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  text-transform: none;
  color: var(--jt-dim);
}
.jt-eyebrow b {
  color: var(--jt-teal);
  font-weight: 600;
}
```

- [ ] **Step 5: 型別與建置驗證**

Run: `cd frontend && npm run build`
Expected: 建置成功（無 TypeScript 錯誤、Vite 產出 `dist/`）。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/theme.ts frontend/src/styles/global.css
git commit -m "feat(fe): 溫暖指揮艙設計基底 token（amber 語意色、層次、圓角、暖化、柔化小標）"
```

---

### Task 2: 可重用元件 EmptyState 與 ReadoutItem（+ 樣式）

**Files:**
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/components/ReadoutItem.tsx`
- Modify: `frontend/src/styles/global.css`（新增 `.jt-dot`、暖化 `.jt-item`、`.jt-empty`）

**Interfaces:**
- Consumes: Task 1 的 `--jt-*` 變數。
- Produces:
  - `EmptyState({ title, description, action? }: { title: string; description: string; action?: React.ReactNode })`
  - `ReadoutItem({ kind, children }: { kind: "pos" | "warn"; children: React.ReactNode })`
  - CSS class `.jt-dot`（圓點標記）、暖化後的 `.jt-item`、`.jt-empty`。

- [ ] **Step 1: 新增圓點標記與暖化空/項目樣式**

在 `global.css` 找到 `.jt-empty`（約第 91–100 行）與 `.jt-item`（約第 108–136 行），用以下整段取代這兩塊（含新增 `.jt-dot`）：

```css
/* 友善空狀態 */
.jt-empty {
  border: 1px dashed var(--jt-border);
  border-radius: var(--jt-radius);
  padding: 36px 24px;
  text-align: center;
  color: var(--jt-muted);
}
.jt-empty .jt-empty-title {
  font-family: "Space Grotesk", sans-serif;
  font-weight: 600;
  font-size: 15px;
  color: var(--jt-text);
  margin-bottom: 6px;
}
.jt-empty .jt-empty-desc {
  font-size: 13px;
  line-height: 1.6;
  max-width: 320px;
  margin: 0 auto;
}

/* 圓點標記：取代 [+] / [!] */
.jt-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 99px;
  margin-top: 7px;
}
.jt-dot[data-kind="pos"] {
  background: var(--jt-teal);
}
.jt-dot[data-kind="warn"] {
  background: var(--jt-amber);
}

/* 診斷項目列：圓點 + 淡色襯底（不再用方括號）*/
.jt-item {
  display: grid;
  grid-template-columns: 16px 1fr;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--jt-radius);
  line-height: 1.55;
  font-size: 14px;
  color: var(--jt-text);
}
.jt-item[data-kind="pos"] {
  background: var(--jt-pos-bg);
}
.jt-item[data-kind="warn"] {
  background: var(--jt-warn-bg);
}
```

- [ ] **Step 2: 建立 ReadoutItem 元件**

`frontend/src/components/ReadoutItem.tsx`：

```tsx
import type { ReactNode } from "react";

/** 診斷項目列：圓點標記 + 淡色襯底。kind=pos 亮點（teal）/ warn 可加強（amber） */
export function ReadoutItem({
  kind,
  children,
}: {
  kind: "pos" | "warn";
  children: ReactNode;
}) {
  return (
    <div className="jt-item" data-kind={kind}>
      <span className="jt-dot" data-kind={kind} aria-hidden />
      <span>{children}</span>
    </div>
  );
}
```

- [ ] **Step 3: 建立 EmptyState 元件**

`frontend/src/components/EmptyState.tsx`：

```tsx
import type { ReactNode } from "react";

/** 友善空狀態：標題 + 說明 +（可選）下一步動作 */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="jt-empty">
      <div className="jt-empty-title">{title}</div>
      <div className="jt-empty-desc">{description}</div>
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}
```

- [ ] **Step 4: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 建置成功（新元件型別正確，無未使用匯入錯誤）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/EmptyState.tsx frontend/src/components/ReadoutItem.tsx frontend/src/styles/global.css
git commit -m "feat(fe): 可重用 EmptyState 與 ReadoutItem（圓點標記、淡色襯底、友善空狀態）"
```

---

### Task 3: ResumeSetup 示範頁套用基底 + 口語文案 + 下一步出口

**Files:**
- Modify: `frontend/src/pages/ResumeSetup.tsx`

**Interfaces:**
- Consumes: Task 2 的 `EmptyState`、`ReadoutItem`；Task 1 的 token。
- Produces: 改版後的「履歷與目標」頁（示範頁）。

- [ ] **Step 1: 匯入新元件並加入路由導向**

在 `ResumeSetup.tsx` 最上方，將 import 區塊補上：

```tsx
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { ReadoutItem } from "../components/ReadoutItem";
```

（移除原本對 `AnalyzingSteps` 以外不再使用的匯入時，以建置錯誤為準逐一清掉。）

- [ ] **Step 2: 暖化頁首文案**

把頁首區塊（原 `{/* Header */}` 的 `Stack`）替換為：

```tsx
<Stack gap={6} mb={32}>
  <span className="jt-eyebrow">第 1 步</span>
  <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
    先讓我認識你
  </Title>
  <Text c="dimmed" fz="sm" maw={560}>
    上傳履歷、填好想找的職位，我就幫你看看「這個職位」上你的亮點，
    還有可以加強的地方。
  </Text>
</Stack>
```

- [ ] **Step 3: 左卡標題與上傳區文案改口語（四態）**

把左卡（輸入面板）的 `jt-panel-head` 與 `FileButton` 區塊替換為：

```tsx
<div className="jt-panel-head">
  <span className="jt-eyebrow">上傳與設定</span>
</div>
<div className="jt-panel-body">
  <Stack gap={18}>
    <FileButton onChange={onFile} accept=".pdf,.docx,.txt">
      {(props) => (
        <UnstyledButton {...props} className="jt-drop" data-loaded={!!resumeText}>
          <Group gap={8} wrap="nowrap">
            <Text fz="sm" fw={500} c="var(--jt-text)">
              {file ? file.name : resumeText ? "✓ 已載入履歷" : "選擇你的履歷檔"}
            </Text>
            {parseMut.isPending && <Loader size={14} color="teal" />}
          </Group>
          <Text fz="xs" c="dimmed">
            {parseMut.isPending
              ? "正在讀取你的履歷…"
              : resumeText
                ? `讀好了 · 共 ${resumeText.length.toLocaleString()} 字`
                : "支援 PDF / DOCX / TXT，點一下或把檔案拖進來"}
          </Text>
        </UnstyledButton>
      )}
    </FileButton>
    {parseMut.isError && (
      <Text fz="xs" c="tangerine.5">
        這個檔案讀不太到，換一個檔案或確認格式再試一次。
      </Text>
    )}

    <TextInput
      label="想找什麼職位？"
      placeholder="例：資深 Python 後端工程師"
      value={title}
      onChange={(e) => setTitle(e.currentTarget.value)}
    />
    <NumberInput
      label="期望月薪（TWD，可留空）"
      placeholder="例：70000"
      value={salary}
      onChange={setSalary}
      thousandSeparator=","
      min={0}
      step={5000}
    />

    <Button color="tangerine" size="md" disabled={!canRun} loading={diagMut.isPending} onClick={run} mt={4}>
      開始診斷
    </Button>
    <Text fz="xs" c="dimmed" ta="center">
      上傳履歷並填好職位後就能開始
    </Text>
  </Stack>
</div>
```

- [ ] **Step 4: 右卡標題、空/錯誤狀態改用 EmptyState，分析中文案暖化**

把右卡（診斷讀數面板）整塊替換為：

```tsx
<div className="jt-panel">
  <div className="jt-panel-head">
    <span className="jt-eyebrow">
      你的診斷結果
      {diagnosis && (
        <>
          {"　"}
          <b style={{ color: "var(--jt-teal)" }}>{diagnosis.strengths.length} 個亮點</b>
          {" · "}
          {diagnosis.gaps.length} 個可加強
        </>
      )}
    </span>
  </div>
  <div className="jt-panel-body" data-center={!diagnosis && !diagMut.isPending}>
    {diagMut.isPending ? (
      <AnalyzingSteps
        steps={[
          "讀取你的履歷與目標…",
          "對著這個職位看你的亮點…",
          "整理可以加強的地方…",
          "彙整成一份診斷…",
        ]}
        intervalSec={4}
      />
    ) : diagMut.isError ? (
      <EmptyState
        title="分析沒成功"
        description="先確認網路或稍後再試一次。"
        action={
          <Button size="xs" variant="default" onClick={run}>
            再試一次
          </Button>
        }
      />
    ) : diagnosis ? (
      <Diagnosis strengths={diagnosis.strengths} gaps={diagnosis.gaps} />
    ) : (
      <EmptyState
        title="還沒有診斷結果"
        description="上傳履歷、填好目標職位，我就幫你看看亮點和可以加強的地方。"
      />
    )}
  </div>
</div>
```

- [ ] **Step 5: 改寫 Diagnosis/Section 用 ReadoutItem、先亮點後可加強，並加「去找職缺」出口**

把檔案底部的 `Diagnosis` 與 `Section` 兩個函式整段替換為：

```tsx
function Diagnosis({ strengths, gaps }: { strengths: string[]; gaps: string[] }) {
  return (
    <Stack gap={22}>
      <Section label="你的亮點" kind="pos" items={strengths} />
      <Section label="可以加強的地方" kind="warn" items={gaps} />
      <Button
        component={Link}
        to="/jobs"
        color="tangerine"
        variant="light"
        size="sm"
        mt={4}
      >
        下一步：去找職缺 →
      </Button>
    </Stack>
  );
}

function Section({
  label,
  kind,
  items,
}: {
  label: string;
  kind: "pos" | "warn";
  items: string[];
}) {
  return (
    <Stack gap={10}>
      <span className="jt-eyebrow">{label}</span>
      <div className="jt-readout">
        {items.map((text, i) => (
          <ReadoutItem key={i} kind={kind}>
            {text}
          </ReadoutItem>
        ))}
      </div>
    </Stack>
  );
}
```

- [ ] **Step 6: 建置驗證**

Run: `cd frontend && npm run build`
Expected: 建置成功，無 TypeScript / 未使用匯入錯誤。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/ResumeSetup.tsx
git commit -m "feat(fe): ResumeSetup 套用溫暖指揮艙基底（口語文案、友善狀態、亮點優先、去找職缺出口）"
```

---

### Task 4: 視覺 QA 與回歸檢查

**Files:**
- 無程式碼變更（必要的小修正回到對應任務的檔案）。

**Interfaces:**
- Consumes: Task 1–3 的成果。

- [ ] **Step 1: 跑起開發伺服器**

Run: `cd frontend && npm run dev`
Expected: Vite 啟動並印出本機網址（例 `http://localhost:5173`）。

- [ ] **Step 2: 截圖檢視示範頁各狀態**

開啟 `/resume`，依序檢視並截圖：
- 左卡：空（未選檔）／解析中／已載入／解析失敗。
- 右卡：空狀態（EmptyState）／分析中（AnalyzingSteps）／有結果（亮點在上、可加強在下、圓點無方括號、底色淡 teal/amber）／錯誤狀態（含「再試一次」）。
- 有結果時出現「下一步：去找職缺 →」並可導向 `/jobs`。

（結果/分析中狀態若需資料，連線後端執行一次真實診斷，或暫時於 `diagMut` 回傳樣本資料截圖後還原。）

- [ ] **Step 3: 無障礙對比抽查**

確認以下達 AA（≥4.5:1，大字 ≥3:1）：
- `--jt-amber #e9a23b` 文字／圓點於 `--jt-warn-bg` 與 panel 底上的可辨識度。
- `--jt-text`、`--jt-muted`、`--jt-dim` 於暖化後的 panel 底上的對比。
不足者回 Task 1 調整變數值後重驗。

- [ ] **Step 4: 回歸檢查（加法式擴充副作用）**

巡視其餘頁面確認未破版：`/jobs`、`/applications`、`/about`、登入頁、側邊導覽。
重點：圓角放大與 `.jt-panel` 陰影是否造成異常；`.jt-item` 改版是否影響仍用舊樣式處
（JobList 的 `.jt-tag` 為獨立 class，不受影響——確認之）。

- [ ] **Step 5: 最終建置驗證並 commit（若有微調）**

Run: `cd frontend && npm run build`
Expected: 成功。如本任務過程有微調，將對應檔案一起 commit：

```bash
git add -A frontend/src
git commit -m "fix(fe): 溫暖指揮艙示範頁視覺 QA 微調"
```

---

## 完成定義（示範階段）

- 設計基底 token 落地且為單一來源。
- EmptyState、ReadoutItem 可重用元件就緒。
- ResumeSetup 完整套用：口語文案、四態上傳、友善空/錯誤、亮點優先、圓點標記、去找職缺出口。
- `npm run build` 通過；各狀態截圖確認；AA 對比達標；其餘頁面未破版。
- 經使用者看過示範頁、確認方向後，再依 spec 的 rollout 清單逐頁推進（另案）。
