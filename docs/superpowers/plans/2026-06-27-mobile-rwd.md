# 手機 RWD 針對性修補 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修補 job-tracker 前端在手機上難用的數處版面（看板、對話框、候選列、觸控目標），桌機版面與所有邏輯維持不變。

**Architecture:** 純前端呈現層修補。以 Mantine `sm`（48em / 768px）為手機↔桌機唯一斷點；結構需切換處用 `useMediaQuery("(max-width: 48em)")`（`@mantine/hooks`），純樣式分流用 Mantine 響應式 props。只改 `Applications.tsx` 與 `JobList.tsx` 兩個檔。

**Tech Stack:** React 18、Mantine 7（`@mantine/core`、`@mantine/hooks`）、TypeScript 5、Vite 6。

## Global Constraints

- 斷點以 Mantine `sm`（`"(max-width: 48em)"`，即 768px）為手機↔桌機唯一分界，與側欄收合一致。
- 不改任何後端 / API client / state（auth、resume）/ 業務邏輯（mutation、query、effect 行為一律不動）。
- 不改桌機（≥sm）版面與互動——所有變更只在 <sm 生效，或在桌機有足夠空間時不產生可見差異。
- 不新增 CSS class；極少量呈現微調可用 inline style。
- 本專案無單元測試框架；驗證閘門為 `cd frontend && npm run build`（`tsc -b && vite build`）通過，外加手動約 375px 寬目視。
- 沿用既有 `.jt-*` token 與既有元件（`AppCard`、`MatchCard`、`CompareButton`、`AppDrawer`）。

---

### Task 1: Applications.tsx 手機版（看板狀態分頁 + 對話框全螢幕 + 比較表橫捲）

**Files:**
- Modify: `frontend/src/pages/Applications.tsx`

**Interfaces:**
- Consumes（既有，不改其定義）：
  - `COLUMNS: { status: ApplicationStatus; label: string }[]`（檔內既有常數）
  - `AppCard({ app }: { app: Application })`
  - `CompareButton({ offers }: { offers: Application[] })`
  - `AppDrawer({ app, opened, onClose }: { app: Application; opened: boolean; onClose: () => void })`
  - `visible: Application[]`（`Applications()` 內既有的關鍵字篩選結果）
- Produces：無（不對外匯出新符號）。

- [ ] **Step 1: 補匯入 `SegmentedControl` 與 `useMediaQuery`**

把 `frontend/src/pages/Applications.tsx` 最上方的兩段匯入改成（在 `@mantine/core` 具名匯入加入 `SegmentedControl`；在 `@mantine/hooks` 匯入加入 `useMediaQuery`）：

```tsx
import {
  ActionIcon, Box, Button, Drawer, Group, Modal, SegmentedControl, Select, Stack, Switch, Table, Text,
  Textarea, TextInput, Title,
} from "@mantine/core";
import { IconCoin, IconMessage, IconX } from "../components/icons";
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
```

- [ ] **Step 2: `Applications()` 內加入手機判斷與選中狀態，並改寫看板呈現**

在 `Applications()` 內 `const kw = query.trim().toLowerCase();` 之上（`const [query, setQuery] = useState("");` 之後）加入：

```tsx
  const isMobile = useMediaQuery("(max-width: 48em)");
  const [mobileStatus, setMobileStatus] = useState<ApplicationStatus>("to_apply");
```

接著把目前的看板區塊（`<Group align="flex-start" gap={14} wrap="nowrap" ...>` 整段，到對應的 `</Group>`）替換為下方的條件渲染。桌機分支與原本完全相同；手機分支用 `SegmentedControl` 切換狀態、單欄垂直排列、移除欄內獨立捲動：

```tsx
      {isMobile ? (
        <>
          <SegmentedControl
            fullWidth
            size="sm"
            mb={16}
            value={mobileStatus}
            onChange={(v) => setMobileStatus(v as ApplicationStatus)}
            data={COLUMNS.map((c) => ({
              value: c.status,
              label: `${c.label} ${visible.filter((a) => a.status === c.status).length}`,
            }))}
          />
          {(() => {
            const col = COLUMNS.find((c) => c.status === mobileStatus)!;
            const items = visible.filter((a) => a.status === mobileStatus);
            return (
              <div className="jt-panel">
                <div className="jt-panel-head">
                  <span className="jt-eyebrow">{col.label} · {items.length}</span>
                  {col.status === "offer" && items.length >= 2 && (
                    <CompareButton offers={items} />
                  )}
                </div>
                <div className="jt-panel-body">
                  <Stack gap={10}>
                    {items.length === 0 ? (
                      <Text fz="xs" c="dimmed" ta="center" py={8}>還沒有</Text>
                    ) : (
                      items.map((a) => <AppCard key={a.job_id} app={a} />)
                    )}
                  </Stack>
                </div>
              </div>
            );
          })()}
        </>
      ) : (
        <Group align="flex-start" gap={14} wrap="nowrap" style={{ overflowX: "auto" }}>
          {COLUMNS.map((col) => {
            const items = visible.filter((a) => a.status === col.status);
            return (
              <div key={col.status} className="jt-panel" style={{ minWidth: 260, flex: 1 }}>
                <div className="jt-panel-head">
                  <span className="jt-eyebrow">{col.label} · {items.length}</span>
                  {col.status === "offer" && items.length >= 2 && (
                    <CompareButton offers={items} />
                  )}
                </div>
                <div
                  className="jt-panel-body"
                  style={{ maxHeight: "calc(100vh - 280px)", overflowY: "auto" }}
                >
                  <Stack gap={10}>
                    {items.length === 0 ? (
                      <Text fz="xs" c="dimmed" ta="center" py={8}>還沒有</Text>
                    ) : (
                      items.map((a) => <AppCard key={a.job_id} app={a} />)
                    )}
                  </Stack>
                </div>
              </div>
            );
          })}
        </Group>
      )}
```

注意：手機分支的單欄 `.jt-panel-body` **不帶** `maxHeight`/`overflowY`，靠整頁捲動（消除巢狀捲動）。桌機分支保留原本欄內捲動。

- [ ] **Step 3: `AppDrawer` 手機改全寬**

在 `AppDrawer({ app, opened, onClose })` 函式內，第一行（`const qc = useQueryClient();` 之前或之後）加入：

```tsx
  const isMobile = useMediaQuery("(max-width: 48em)");
```

並把該函式的 `<Drawer ... size="md" ...>` 改為 `size={isMobile ? "100%" : "md"}`，其餘 props 不變：

```tsx
    <Drawer opened={opened} onClose={onClose} position="right" size={isMobile ? "100%" : "md"}
            title={<span className="jt-eyebrow">{app.job.company} · {app.job.title}</span>}>
```

- [ ] **Step 4: `CompareButton` 手機全螢幕 + 比較表橫向捲動**

在 `CompareButton({ offers })` 函式內，`const [opened, { open, close }] = useDisclosure(false);` 之後加入：

```tsx
  const isMobile = useMediaQuery("(max-width: 48em)");
```

把該函式的 `<Modal ... size="lg" ...>` 改為加上 `fullScreen={isMobile}`（保留 `size="lg"` 供桌機用）：

```tsx
      <Modal opened={opened} onClose={close} size="lg" fullScreen={isMobile}
             title={<span className="jt-eyebrow">Offer 比較</span>}>
```

再把該 Modal 內的 `<Table ...>...</Table>` 整段用 `Table.ScrollContainer` 包起來（窄螢幕表格自身可橫捲、不撐破容器）：

```tsx
        <Table.ScrollContainer minWidth={480}>
          <Table withTableBorder withColumnBorders fz="xs">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>公司</Table.Th>
                <Table.Th>薪資</Table.Th>
                <Table.Th>職等</Table.Th>
                <Table.Th>到職日</Table.Th>
                <Table.Th>備註</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {offers.map((a) => (
                <Table.Tr key={a.job_id}>
                  <Table.Td>{a.job.company}</Table.Td>
                  <Table.Td>{a.offer?.salary ?? "—"}</Table.Td>
                  <Table.Td>{a.offer?.level ?? "—"}</Table.Td>
                  <Table.Td>{a.offer?.start_date ?? "—"}</Table.Td>
                  <Table.Td>{a.offer?.note ?? "—"}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
```

- [ ] **Step 5: 建置驗證**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` 無型別錯誤、`✓ built` 成功（無新增 error/warning）。

- [ ] **Step 6: 手動目視（約 375px 寬）**

在瀏覽器 devtools 設約 375px 寬開啟 `/applications`：
- 看板上方出現 `SegmentedControl`（5 個狀態含筆數），切換可換顯示對應單欄。
- 單欄卡片垂直排列、靠整頁捲動，無「捲中捲」。
- 切到 Offer 欄且有 ≥2 筆時出現「比較」，點開為全螢幕、表格可左右捲。
- 點卡片開 Offer 編輯 Drawer 為全寬。
- 桌機（≥768px）回看：仍為 5 欄橫向看板、欄內捲動、Drawer/Modal 尺寸如舊。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Applications.tsx
git commit -m "feat(rwd): Applications 手機版看板狀態分頁、對話框全螢幕、比較表橫捲"
```

---

### Task 2: JobList.tsx 手機版（求職信 Modal 全螢幕 + 候選列兩行式 + 主要按鈕觸控尺寸）

**Files:**
- Modify: `frontend/src/pages/JobList.tsx`

**Interfaces:**
- Consumes（既有，不改其定義）：
  - `candidates`（`JobList()` 內既有，型別 `JobMatch[]` 的子集，元素含 `c.job.job_id`、`c.job.url`、`c.job.title`、`c.job.company`、`c.job.salary`、`c.relevant`）
  - `picked: Set<string>`、`toggle(id: string)`、`crawlMut`、`analyzeMut`、`busy`、`pickedCandidates`、`candOpen`、`setCandOpen`（皆 `JobList()` 內既有）
  - `MatchCard({ match, searchId })`（檔內既有）
- Produces：無。

- [ ] **Step 1: 補匯入 `useMediaQuery`**

把 `frontend/src/pages/JobList.tsx` 的 `import { useDisclosure } from "@mantine/hooks";` 改為：

```tsx
import { useDisclosure, useMediaQuery } from "@mantine/hooks";
```

- [ ] **Step 2: `JobList()` 內加入手機判斷**

在 `JobList()` 內 `const qc = useQueryClient();`（約現行第 52 行）之後加入：

```tsx
  const isMobile = useMediaQuery("(max-width: 48em)");
```

- [ ] **Step 3: 候選面板標頭允許換行 + 主要按鈕手機放大**

把候選清單面板的標頭區塊（現行 `<div className="jt-panel-head"><span className="jt-eyebrow">有興趣的候選 · {candidates.length}</span><Group gap={8}>...</Group></div>`）替換為下方版本：標頭允許換行（`flexWrap`/`rowGap` inline），「爬下一頁」「分析選中」在手機放大到 `sm`、桌機維持 `xs`；「收合」維持 `xs`：

```tsx
              <div className="jt-panel-head" style={{ flexWrap: "wrap", rowGap: 8 }}>
                <span className="jt-eyebrow">有興趣的候選 · {candidates.length}</span>
                <Group gap={8} wrap="wrap">
                  <Button size="xs" variant="subtle" color="gray"
                          onClick={() => setCandOpen((o) => !o)}>
                    {candOpen ? "▾ 收合" : "▸ 展開"}
                  </Button>
                  <Button size={isMobile ? "sm" : "xs"} variant="default" onClick={() => crawlMut.mutate()}
                          disabled={busy} loading={crawlMut.isPending}>爬下一頁</Button>
                  <Button size={isMobile ? "sm" : "xs"} color="tangerine"
                          disabled={pickedCandidates.length === 0 || analyzeMut.isPending}
                          loading={analyzeMut.isPending}
                          onClick={() => analyzeMut.mutate()}>
                    分析選中（{pickedCandidates.length}）
                  </Button>
                </Group>
              </div>
```

- [ ] **Step 4: 候選列改兩行式（不被壓扁）**

把候選列的 `candidates.map(...)` 區塊（現行單行 `<Group key={c.job.job_id} gap={10} wrap="nowrap">` 內含 checkbox、標題 `a`、公司、薪資、廣告 chip）替換為下方版本：checkbox 在左對齊頂端，右側第一行職稱、第二行公司 · 薪資 · 標籤（窄螢幕自動換行）。此結構桌機手機共用：

```tsx
                  {candidates.map((c) => (
                    <Group key={c.job.job_id} gap={10} wrap="nowrap" align="flex-start">
                      <Checkbox
                        mt={2}
                        checked={picked.has(c.job.job_id)}
                        onChange={() => toggle(c.job.job_id)}
                      />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <a className="jt-job-title" href={c.job.url} target="_blank" rel="noreferrer"
                           style={{ display: "block" }}>{c.job.title}</a>
                        <Group gap={8} wrap="wrap" mt={2}>
                          <Text fz="xs" c="dimmed">{c.job.company}</Text>
                          {c.job.salary && <Text fz="xs" c="dimmed">· {c.job.salary}</Text>}
                          {!c.relevant && (
                            <span className="jt-chip" style={{ color: "var(--jt-dim)" }}>廣告？</span>
                          )}
                        </Group>
                      </div>
                    </Group>
                  ))}
```

- [ ] **Step 5: 求職信 Modal 手機全螢幕**

在 `MatchCard({ match, searchId })` 函式內，`const [opened, { open, close }] = useDisclosure(false);` 之後加入：

```tsx
  const isMobile = useMediaQuery("(max-width: 48em)");
```

把該函式的求職信 `<Modal ... size="lg" ...>` 改為加上 `fullScreen={isMobile}`（保留 `size="lg"`、其餘 props 不變）：

```tsx
      <Modal
        opened={opened}
        onClose={close}
        size="lg"
        fullScreen={isMobile}
        closeOnClickOutside={!letterMut.isPending}
        closeOnEscape={!letterMut.isPending}
        title={
          <span className="jt-eyebrow">
            求職信 // {job.company} · {job.title}
          </span>
        }
      >
```

- [ ] **Step 6: 建置驗證**

Run: `cd frontend && npm run build`
Expected: `tsc -b && vite build` 無型別錯誤、`✓ built` 成功（無新增 error/warning）。

- [ ] **Step 7: 手動目視（約 375px 寬）**

在約 375px 寬開啟 `/jobs`（需有履歷與一筆搜尋；候選清單出現時）：
- 候選面板標頭按鈕不溢出（必要時換到第二行）；「分析選中」「爬下一頁」明顯較大、好點。
- 候選列為兩行式：職稱一行、公司/薪資/標籤折在下一行，職稱不被壓扁。
- 展開某筆結果 → 開「生成求職信」Modal 為全螢幕、內容不溢出。
- 桌機（≥768px）回看：候選列兩行式（桌機亦成立、更清楚）、按鈕為 `xs`、Modal 尺寸如舊。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/JobList.tsx
git commit -m "feat(rwd): JobList 手機版求職信 Modal 全螢幕、候選列兩行式、主要按鈕觸控尺寸"
```

---

## 完成後

兩個任務完成後，手機 RWD 針對性修補即完成。最終由 subagent-driven 的全分支 review 把關，再以 finishing-a-development-branch 決定合併/推送。
