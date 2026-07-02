# career-sentinel UI/UX 整體改版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 前端整體改版為「Cockpit 色系 × Exaggerated Minimalism 版面 × 左側欄」——theme.ts 主題、AppShell 側欄（全域重新抓取）、六頁重整、Tabler icon 全面替換 emoji。

**Architecture:** 純前端（`sentinel/web/frontend/`）。Task 1 主題基座 → Task 2 AppShell 側欄＋全域邏輯上移 → Task 3–6 各頁重整 → Task 7 真機驗收。後端 API、資料流零變動。

**Tech Stack:** React 18 + Vite + Mantine 7 + TanStack Query + @tabler/icons-react（新增）。

**Spec:** `docs/superpowers/specs/2026-07-02-career-sentinel-uiux-redesign-design.md`

## Global Constraints

- **後端零變動**：不碰 `sentinel/src/`；後端 191 測試全程保持綠（不用重跑，最後 Task 7 跑一次確認）。
- 每個任務的驗證關卡＝`cd sentinel/web/frontend && npm run build` **零 TS 錯誤**。
- 色彩語意：**tangerine＝行動**（每頁至多一顆實心主按鈕、★關注、active 點綴）、**teal＝正向訊號**（分數、時間、+N）、**amber＝警示**（邀約、提醒橫幅）、**danger＝錯誤**。深色 only。
- 字體：標題/KPI＝Space Grotesk、內文＝IBM Plex Sans、數字/時間＝IBM Plex Mono。
- 版面：KPI 大字級（48–56px、letter-spacing -2~-3px）；面板去 `withBorder` 改扁平色塊 `bg="dark.6"` + radius 8；頁 padding 32px+。
- **Icon 一律 Tabler SVG**，UI 中不得以 emoji 當 icon（🧠🧹✕★⚠️ 等全換；`notify()` 的 OS 通知文字內 emoji 可留）。
- 互動：可點元素 cursor-pointer（Mantine Button/NavLink/ActionIcon 內建）、hover 過渡 150–300ms、不用會位移的 scale、不關閉 focus ring。
- **行為不變**：scrape 輪詢/通知/排程橫幅/聊天串流與「切頁不丟聊天狀態」等既有行為全部保留，只搬位置與換皮。
- 工作分支 `dev`；commit 風格 `feat(sentinel): ...（SP-UIUX）`；commit 訊息尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。

---

## File Structure

- Create: `sentinel/web/frontend/src/theme.ts`（Cockpit 主題）
- Create: `sentinel/web/frontend/src/ui.tsx`（PageHeader / Kpi 共用元件）
- Create: `sentinel/web/frontend/src/Sidebar.tsx`（側欄：導覽＋設定＋全域重新抓取）
- Modify: `index.html`（字體）、`main.tsx`（套 theme）、`App.tsx`（AppShell 重寫）
- Modify: `Dashboard.tsx`（Task 2 瘦身、Task 3 重設計）、`ResumePage.tsx`、`MatchPage.tsx`、`RecommendPage.tsx`、`SearchPage.tsx`、`JobRow.tsx`、`ChatPage.tsx`、`chat-md.css`
- 不動：`api.ts`、`notify.ts`、`SettingsModal.tsx`（Modal 自動吃新主題）

所有指令在 `sentinel/web/frontend/` 執行（除最後 pytest）。

---

### Task 1: 主題基座（theme.ts + 字體 + icons 套件）

**Files:**
- Create: `sentinel/web/frontend/src/theme.ts`
- Modify: `sentinel/web/frontend/index.html`
- Modify: `sentinel/web/frontend/src/main.tsx`

**Interfaces:**
- Produces: `theme`（named export，含 colors `tangerine/teal/amber/danger`、`dark`=ink 覆寫、primaryColor tangerine、字體設定）。後續任務可用 `c="teal.5"`、`c="amber.5"`、`color="tangerine"` 與 `bg="dark.6"`。

- [ ] **Step 1: 安裝 @tabler/icons-react**

```bash
cd sentinel/web/frontend && npm install @tabler/icons-react
```

- [ ] **Step 2: 建立 theme.ts**（`sentinel/web/frontend/src/theme.ts` 新檔——色值自雲端 `frontend/src/theme.ts` 逐字複製）

```ts
import { createTheme, type MantineColorsTuple } from "@mantine/core";

// Cockpit 指揮艙（自雲端 career_agent 移植）：冷 ink 底 + 雙訊號色（tangerine 行動 / teal 契合）

const tangerine: MantineColorsTuple = [
  "#fff0eb", "#ffd9cc", "#ffb59e", "#ff8f6f", "#ff7048",
  "#ff6a3d", "#f15a2c", "#cf4a22", "#a83b1a", "#7d2b12",
];

const teal: MantineColorsTuple = [
  "#e1fbf6", "#bff3ea", "#92ebdd", "#5fe2cf", "#3fd9c5",
  "#34d6c8", "#22b3a6", "#198f86", "#136d66", "#0c4a45",
];

const amber: MantineColorsTuple = [
  "#fff8ec", "#fcedd2", "#f6d9a6", "#f1c576", "#ecb34f",
  "#e9a23b", "#d98f2a", "#b67322", "#925b1c", "#6f4413",
];

const danger: MantineColorsTuple = [
  "#fff0f0", "#ffe0e0", "#fbc4c4", "#f5a3a3", "#f08585",
  "#ec6f6f", "#e85d5d", "#cf4848", "#b83b3b", "#9e2e2e",
];

// 覆寫 Mantine dark 色階 → 整個深色介面用 ink 調
const ink: MantineColorsTuple = [
  "#e8e6e3", // 0 主要文字
  "#c6c3c6", // 1
  "#a3a0a6", // 2 muted
  "#969399", // 3 dim
  "#302d34", // 4 邊框
  "#262329", // 5 面板2
  "#201f24", // 6 面板
  "#15151a", // 7 body 背景
  "#101013", // 8
  "#0a0a0c", // 9
];

export const theme = createTheme({
  fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
  fontFamilyMonospace: "'IBM Plex Mono', ui-monospace, monospace",
  headings: { fontFamily: "'Space Grotesk', system-ui, sans-serif" },
  primaryColor: "tangerine",
  primaryShade: 5,
  defaultRadius: "md",
  colors: { tangerine, teal, amber, danger, dark: ink },
});
```

- [ ] **Step 3: index.html 引入字體**（`<title>` 之後、`</head>` 之前插入）

```html
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono:wght@500&display=swap" rel="stylesheet" />
```

- [ ] **Step 4: main.tsx 套 theme**（全檔改為）

```tsx
import { MantineProvider } from "@mantine/core";
import "@mantine/core/styles.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { theme } from "./theme";

const qc = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark">
      <QueryClientProvider client={qc}>
        <App />
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 5: build 驗證**

Run: `npm run build`
Expected: 零 TS 錯誤（畫面已全域變 ink 調＋tangerine 主色）

- [ ] **Step 6: Commit**

```bash
git add src/theme.ts src/main.tsx index.html package.json package-lock.json
git commit -m "feat(sentinel): Cockpit 主題基座——theme.ts + 字體 + tabler icons（SP-UIUX）"
```

---

### Task 2: AppShell 側欄 + 全域重新抓取/提醒橫幅上移

**Files:**
- Create: `sentinel/web/frontend/src/ui.tsx`
- Create: `sentinel/web/frontend/src/Sidebar.tsx`
- Modify: `sentinel/web/frontend/src/App.tsx`（全檔重寫）
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`（瘦身：header/橫幅/通知/scrape 邏輯移出）

**Interfaces:**
- Consumes: Task 1 的 theme；既有 `api.ts`（`getStatus/getSchedule/ackSchedule/startScrape/getSnapshot`）、`notify.ts`（`ensurePermission/notify`）、`SettingsModal`。
- Produces: `ui.tsx` 的 `PageHeader({title, subtitle?, action?})` 與 `Kpi({value, label, suffix?})`；`Sidebar.tsx` 的 `PageKey = "dashboard"|"resume"|"match"|"recommend"|"search"|"chat"` 與 default export `Sidebar`；`Dashboard` 改為無 props。

- [ ] **Step 1: 建立 ui.tsx**

```tsx
import { Group, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, action }: {
  title: string; subtitle?: string; action?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-end" mb="xl">
      <Stack gap={4}>
        <Title order={2} style={{ letterSpacing: "-0.5px" }}>{title}</Title>
        {subtitle && <Text size="sm" c="dimmed">{subtitle}</Text>}
      </Stack>
      {action}
    </Group>
  );
}

export function Kpi({ value, label, suffix }: {
  value: ReactNode; label: string; suffix?: ReactNode;
}) {
  return (
    <div>
      <div style={{
        fontFamily: "'Space Grotesk', sans-serif", fontSize: 52, fontWeight: 700,
        letterSpacing: "-3px", lineHeight: 1, color: "var(--mantine-color-dark-0)",
        display: "flex", alignItems: "baseline", gap: 8,
      }}>
        <span>{value}</span>
        {suffix}
      </div>
      <Text size="xs" c="dimmed" mt={8} style={{ letterSpacing: 2 }}>{label}</Text>
    </div>
  );
}
```

- [ ] **Step 2: 建立 Sidebar.tsx**

```tsx
import { Button, NavLink, Stack, Text } from "@mantine/core";
import {
  IconArrowsExchange, IconFileText, IconLayoutDashboard, IconMessageCircle,
  IconRefresh, IconSearch, IconSettings, IconStars,
} from "@tabler/icons-react";

export type PageKey = "dashboard" | "resume" | "match" | "recommend" | "search" | "chat";

const NAV: { key: PageKey; label: string; icon: typeof IconSearch }[] = [
  { key: "dashboard", label: "儀表板", icon: IconLayoutDashboard },
  { key: "resume", label: "履歷健檢", icon: IconFileText },
  { key: "match", label: "JD 比對", icon: IconArrowsExchange },
  { key: "recommend", label: "推薦", icon: IconStars },
  { key: "search", label: "職缺搜尋", icon: IconSearch },
  { key: "chat", label: "整理助手", icon: IconMessageCircle },
];

export default function Sidebar({ page, onNavigate, onRefresh, running, lastRun, onOpenSettings }: {
  page: PageKey;
  onNavigate: (p: PageKey) => void;
  onRefresh: () => void;
  running: boolean;
  lastRun: string | null;
  onOpenSettings: () => void;
}) {
  return (
    <Stack h="100%" gap={2} p="sm">
      <Text px="sm" pb="lg" style={{
        fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 15, letterSpacing: 2,
      }}>
        SENTINEL<Text span c="tangerine.5" inherit>_</Text>
      </Text>
      {NAV.map(({ key, label, icon: Icon }) => (
        <NavLink
          key={key}
          active={page === key}
          onClick={() => onNavigate(key)}
          label={label}
          leftSection={<Icon size={17} stroke={1.7} />}
          variant="light"
          color="gray"
          style={{ borderRadius: 8 }}
        />
      ))}
      <Stack mt="auto" gap={6}>
        <Button variant="subtle" color="gray" size="xs"
          leftSection={<IconSettings size={15} />} onClick={onOpenSettings}>
          設定
        </Button>
        <Button leftSection={<IconRefresh size={16} />}
          onClick={onRefresh} loading={running} disabled={running}>
          重新抓取
        </Button>
        <Text size="xs" c="dimmed" ta="center" ff="monospace">上次 {lastRun ?? "—"}</Text>
      </Stack>
    </Stack>
  );
}
```

- [ ] **Step 3: App.tsx 全檔重寫**（scrape 輪詢/完成通知、排程 due 通知與橫幅——原封自 Dashboard 搬來，邏輯不變）

```tsx
import { Alert, AppShell, Button, Group } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ackSchedule, getSchedule, getStatus, startScrape } from "./api";
import ChatPage from "./ChatPage";
import Dashboard from "./Dashboard";
import MatchPage from "./MatchPage";
import { ensurePermission, notify } from "./notify";
import RecommendPage from "./RecommendPage";
import ResumePage from "./ResumePage";
import SearchPage from "./SearchPage";
import SettingsModal from "./SettingsModal";
import Sidebar, { type PageKey } from "./Sidebar";

export default function App() {
  const qc = useQueryClient();
  const [page, setPage] = useState<PageKey>("dashboard");
  const [polling, setPolling] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const prevDue = useRef(false);
  const notifyOnDone = useRef(false);

  const status = useQuery({
    queryKey: ["status"], queryFn: getStatus,
    refetchInterval: polling ? 2000 : false,
  });
  const schedule = useQuery({ queryKey: ["schedule"], queryFn: getSchedule, refetchInterval: 30000 });

  useEffect(() => { ensurePermission(); }, []);

  // 到點：due false→true 邊緣 → 桌面通知（橫幅由 schedule.data.due 直接驅動）
  useEffect(() => {
    const due = schedule.data?.due ?? false;
    if (due && !prevDue.current) {
      notify("⏰ career-sentinel", "該檢視求職動態了，點「立即拉取」更新。");
    }
    prevDue.current = due;
  }, [schedule.data?.due]);

  // scrape 完成：running true→false 邊緣 → 讀新增計數發通知
  useEffect(() => {
    if (polling && status.data && !status.data.running) {
      setPolling(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
      const c = status.data.last_change_counts;
      const total = c ? c.new_viewers + c.status_changes + c.new_messages + c.new_invites : 0;
      if (notifyOnDone.current && !status.data.last_error && total > 0) {
        notify("🔔 career-sentinel", `發現 ${total} 筆新動態（看過我／訊息／狀態變化）。`);
      }
      notifyOnDone.current = false;
    }
  }, [polling, status.data, qc]);

  async function refresh() {
    const r = await startScrape();
    notifyOnDone.current = r.status !== "already_running";
    setPolling(true);
  }

  async function onBannerPull() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
    await refresh();
  }

  async function onBannerDismiss() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
  }

  const running = polling || !!status.data?.running;
  const due = schedule.data?.due ?? false;

  return (
    <AppShell navbar={{ width: 200, breakpoint: 0 }} padding={0}>
      <AppShell.Navbar>
        <Sidebar
          page={page}
          onNavigate={setPage}
          onRefresh={refresh}
          running={running}
          lastRun={status.data?.last_run ?? null}
          onOpenSettings={() => setSettingsOpen(true)}
        />
      </AppShell.Navbar>
      <AppShell.Main>
        {due && (
          <Alert color="amber" m="md" mb={0} withCloseButton onClose={onBannerDismiss} title="該檢視求職動態了">
            <Group>
              <Button size="xs" onClick={onBannerPull} loading={running} disabled={running}>立即拉取</Button>
              <Button size="xs" variant="light" onClick={() => setPage("recommend")}>也拉推薦</Button>
            </Group>
          </Alert>
        )}
        {page === "dashboard" && <Dashboard />}
        {page === "resume" && <ResumePage />}
        {page === "match" && <MatchPage />}
        {page === "recommend" && <RecommendPage />}
        {page === "search" && <SearchPage />}
        {/* 聊天頁：display:none 隱藏而非卸載——保住串流/訊息狀態（原 keepMounted 行為） */}
        <div style={{ display: page === "chat" ? undefined : "none" }}><ChatPage /></div>
      </AppShell.Main>
      <SettingsModal opened={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </AppShell>
  );
}
```

- [ ] **Step 4: Dashboard.tsx 瘦身**（全檔改為——只刪搬走的東西，版面 Task 3 才重設計）

```tsx
import { Anchor, Badge, Button, Card, Container, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { type Interview, getSnapshot, getStatus } from "./api";

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card withBorder padding="md" radius="md" style={{ flex: 1, minWidth: 280 }}>
      <Title order={4} mb="sm">{title}（{count}）</Title>
      <Stack gap={8}>{children}</Stack>
    </Card>
  );
}

export default function Dashboard() {
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({ queryKey: ["status"], queryFn: getStatus });
  const s = snap.data;

  return (
    <Container size="lg" py="lg">
      <Group justify="space-between" mb="md">
        <Title order={2}>儀表板</Title>
        <Text size="sm" c="dimmed">上次更新：{s?.run_at ?? "—"}</Text>
      </Group>

      {status.data?.last_error && (
        <Text c="red" mb="sm">{status.data.last_error}</Text>
      )}
      {s && s.failed_readers.length > 0 && (
        <Text c="orange" mb="sm">本次未讀到：{s.failed_readers.join("、")}（沿用上次）</Text>
      )}

      {s && s.interviews.length > 0 && (
        <Card withBorder padding="md" radius="md" mb="md">
          <Title order={4} mb="sm">即將到來的面試（{s.interviews.length}）</Title>
          <Stack gap="xs">
            {s.interviews.map((iv: Interview, i: number) => (
              <Group key={i} justify="space-between" wrap="nowrap">
                <div>
                  <Text fw={600}>{iv.company}　<Text span c="dimmed" size="sm">{iv.job_title}</Text></Text>
                  <Text size="sm" c="dimmed">
                    {iv.when || "日期未擷取"}{iv.location ? ` · ${iv.location}` : ""}
                  </Text>
                </div>
                <Group gap="xs" wrap="nowrap">
                  {iv.job_url && <Anchor href={iv.job_url} target="_blank" size="sm">看職缺</Anchor>}
                  <Button component="a" href={iv.gcal_link} target="_blank" size="xs" variant="light">加入 Google 日曆</Button>
                </Group>
              </Group>
            ))}
          </Stack>
        </Card>
      )}

      <Card withBorder padding="md" radius="md" mb="md">
        <Title order={4} mb="xs">今日彙整</Title>
        <Text style={{ whiteSpace: "pre-wrap" }}>{s?.digest ?? "載入中…"}</Text>
      </Card>

      <Group align="flex-start" gap="md" wrap="wrap">
        <Panel title="誰看過我" count={s?.viewers.length ?? 0}>
          {s?.viewers.map((v, i) => (
            <Text key={i} size="sm">{v.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}{v.company}　<Text span c="dimmed">{v.job_title} · {v.viewed_at}</Text></Text>
          ))}
        </Panel>
        <Panel title="我的應徵" count={s?.applications.length ?? 0}>
          {s?.applications.map((a) => (
            <Text key={a.job_id} size="sm">{a.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}{a.company} · {a.title}　<Badge size="sm" variant="light">{a.status}</Badge></Text>
          ))}
        </Panel>
        <Panel title="訊息 · 面試" count={s?.messages.length ?? 0}>
          {s?.messages.map((m) => (
            <Text key={m.thread_id} size="sm">
              {m.has_interview_invite && <Badge size="sm" color="orange" mr={6}>面試</Badge>}
              {m.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}
              {m.company}：<Text span c="dimmed">{m.last_message}</Text>
            </Text>
          ))}
        </Panel>
      </Group>
    </Container>
  );
}
```

- [ ] **Step 5: build 驗證**

Run: `npm run build`
Expected: 零 TS 錯誤（側欄出現、六頁可切、重新抓取在側欄底部、聊天切頁不丟狀態）

- [ ] **Step 6: Commit**

```bash
git add src/ui.tsx src/Sidebar.tsx src/App.tsx src/Dashboard.tsx
git commit -m "feat(sentinel): AppShell 左側欄——全域重新抓取/提醒橫幅上移 App 層（SP-UIUX）"
```

---

### Task 3: 儀表板重設計（大字級 KPI + 扁平清單）

**Files:**
- Modify: `sentinel/web/frontend/src/Dashboard.tsx`（全檔重寫）

**Interfaces:**
- Consumes: `ui.tsx` 的 `Kpi`；既有 `api.ts` 型別；theme 色。
- Produces: 無（頁面末端）。

- [ ] **Step 1: Dashboard.tsx 全檔重寫**

```tsx
import { ActionIcon, Anchor, Badge, Box, Group, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconCalendarPlus, IconStarFilled } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { type Interview, getSnapshot, getStatus } from "./api";
import { Kpi } from "./ui";

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <Title order={5} mt={36} mb="sm" style={{ letterSpacing: "-0.3px" }}>
      {children}
      {hint && <Text span size="xs" c="dimmed" fw={400} ml={8}>{hint}</Text>}
    </Title>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <Group justify="space-between" wrap="nowrap" px="md" py={10} mb={6}
      bg="dark.6" style={{ borderRadius: 8, transition: "background-color 200ms" }}>
      {children}
    </Group>
  );
}

const Star = () => (
  <IconStarFilled size={12} style={{ color: "var(--mantine-color-tangerine-5)", flexShrink: 0 }} />
);

export default function Dashboard() {
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({ queryKey: ["status"], queryFn: getStatus });
  const s = snap.data;
  const invites = s?.messages.filter((m) => m.has_interview_invite).length ?? 0;
  const newViewers = status.data?.last_change_counts?.new_viewers ?? 0;

  return (
    <Box p={36} maw={1080}>
      <Group gap={52} align="flex-start">
        <Kpi
          value={s?.viewers.length ?? "—"}
          label="誰看過我"
          suffix={newViewers > 0 ? <Text span c="teal.5" ff="monospace" size="md">+{newViewers}</Text> : undefined}
        />
        <Kpi value={s?.interviews.length ?? "—"} label="即將面試" />
        <Kpi
          value={s?.messages.length ?? "—"}
          label="新訊息"
          suffix={invites > 0 ? <Text span c="amber.5" ff="monospace" size="md">{invites} 邀約</Text> : undefined}
        />
        <Kpi value={s?.applications.length ?? "—"} label="投遞中" />
      </Group>

      {status.data?.last_error && (
        <Group gap={6} mt="lg">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-danger-6)" }} />
          <Text c="danger.6" size="sm">{status.data.last_error}</Text>
        </Group>
      )}
      {s && s.failed_readers.length > 0 && (
        <Group gap={6} mt="sm">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-amber-5)" }} />
          <Text c="amber.5" size="sm">本次未讀到：{s.failed_readers.join("、")}（沿用上次）</Text>
        </Group>
      )}

      {s && s.interviews.length > 0 && (
        <>
          <SectionTitle>即將到來的面試</SectionTitle>
          {s.interviews.map((iv: Interview, i: number) => (
            <Row key={i}>
              <Text size="sm" truncate>
                <Text span fw={600}>{iv.company}</Text>
                <Text span c="dimmed"> · {iv.job_title}{iv.location ? ` · ${iv.location}` : ""}</Text>
              </Text>
              <Group gap="md" wrap="nowrap">
                <Text c="teal.5" ff="monospace" size="xs">{iv.when || "日期未擷取"}</Text>
                {iv.job_url && <Anchor href={iv.job_url} target="_blank" size="xs" c="dimmed">看職缺</Anchor>}
                <ActionIcon component="a" href={iv.gcal_link} target="_blank"
                  variant="default" size="md" title="加入 Google 日曆">
                  <IconCalendarPlus size={15} />
                </ActionIcon>
              </Group>
            </Row>
          ))}
        </>
      )}

      <SectionTitle hint={s?.run_at ? `上次更新 ${s.run_at}` : undefined}>誰看過我</SectionTitle>
      {s?.viewers.map((v, i) => (
        <Row key={i}>
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            {v.watched && <Star />}
            <Text size="sm" truncate>
              <Text span fw={600}>{v.company}</Text>
              <Text span c="dimmed"> · {v.job_title}</Text>
            </Text>
          </Group>
          <Text c="dimmed" ff="monospace" size="xs">{v.viewed_at}</Text>
        </Row>
      ))}

      <SectionTitle>我的應徵</SectionTitle>
      {s?.applications.map((a) => (
        <Row key={a.job_id}>
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            {a.watched && <Star />}
            <Text size="sm" truncate>
              <Text span fw={600}>{a.company}</Text>
              <Text span c="dimmed"> · {a.title}</Text>
            </Text>
          </Group>
          <Badge size="sm" variant="light" color="teal">{a.status}</Badge>
        </Row>
      ))}

      <SectionTitle>訊息 · 面試</SectionTitle>
      {s?.messages.map((m) => (
        <Row key={m.thread_id}>
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            {m.has_interview_invite && <Badge size="xs" variant="light" color="amber">面試</Badge>}
            {m.watched && <Star />}
            <Text size="sm" truncate>
              <Text span fw={600}>{m.company}</Text>
              <Text span c="dimmed">：{m.last_message}</Text>
            </Text>
          </Group>
        </Row>
      ))}

      <SectionTitle>今日彙整</SectionTitle>
      <Text size="sm" c="dark.2" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
        {s?.digest ?? "載入中…"}
      </Text>
    </Box>
  );
}
```

- [ ] **Step 2: build 驗證**

Run: `npm run build`
Expected: 零 TS 錯誤

- [ ] **Step 3: Commit**

```bash
git add src/Dashboard.tsx
git commit -m "feat(sentinel): 儀表板重設計——大字級 KPI + 扁平清單（SP-UIUX）"
```

---

### Task 4: 履歷健檢 + JD 比對重整

**Files:**
- Modify: `sentinel/web/frontend/src/ResumePage.tsx`（全檔重寫）
- Modify: `sentinel/web/frontend/src/MatchPage.tsx`（全檔重寫）

**Interfaces:**
- Consumes: `ui.tsx` 的 `PageHeader`；既有 api 函式簽名不變。

- [ ] **Step 1: ResumePage.tsx 全檔重寫**（邏輯不變，只換版面；診斷結果雙欄 teal/amber）

```tsx
import {
  Button, FileInput, Grid, Group, List, NumberInput, Paper, Stack, Text, TextInput, ThemeIcon,
} from "@mantine/core";
import { IconAlertTriangle, IconCheck } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { diagnoseResume, getResume, uploadResume } from "./api";
import { PageHeader } from "./ui";

export default function ResumePage() {
  const qc = useQueryClient();
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (resume.data) {
      setTitle(resume.data.target_title);
      setSalary(resume.data.expected_salary ?? "");
    }
  }, [resume.data]);

  async function onUpload(file: File | null) {
    if (!file) return;
    setErr(null);
    const r = await uploadResume(file);
    if (!r.ok) { setErr("履歷上傳失敗（僅支援 PDF / TXT）"); return; }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  async function runDiagnose() {
    setErr(null);
    setBusy(true);
    const r = await diagnoseResume(title, salary === "" ? null : Number(salary));
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "健檢失敗");
      return;
    }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  const d = resume.data?.diagnosis;
  return (
    <Stack p={36} maw={860}>
      <PageHeader title="履歷健檢" subtitle="上傳履歷，針對目標職位產出優勢與待補強清單" />
      <Paper bg="dark.6" radius="md" p="lg">
        <Stack>
          <FileInput label="上傳履歷（PDF / TXT）" placeholder="選擇檔案" accept=".pdf,.txt" onChange={onUpload} />
          <Text size="sm" c="dimmed">{resume.data?.has_resume ? `已載入 ${resume.data.chars} 字` : "尚未上傳履歷"}</Text>
          <Group grow>
            <TextInput label="目標職稱" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
            <NumberInput label="期望月薪（選填）" value={salary} onChange={(v) => setSalary(typeof v === "number" ? v : "")} />
          </Group>
          {err && <Text c="danger.6" size="sm">{err}</Text>}
          <Button onClick={runDiagnose} loading={busy} w="fit-content"
            disabled={!resume.data?.has_resume || !title.trim()}>
            執行健檢
          </Button>
        </Stack>
      </Paper>
      {d && (
        <Grid mt="md">
          <Grid.Col span={6}>
            <Paper bg="dark.6" radius="md" p="lg" h="100%">
              <Group gap={8} mb="sm">
                <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                <Text fw={600}>優勢</Text>
              </Group>
              <List size="sm" spacing={6}>{d.strengths.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
            </Paper>
          </Grid.Col>
          <Grid.Col span={6}>
            <Paper bg="dark.6" radius="md" p="lg" h="100%">
              <Group gap={8} mb="sm">
                <ThemeIcon variant="light" color="amber" size="sm"><IconAlertTriangle size={13} /></ThemeIcon>
                <Text fw={600}>待補強</Text>
              </Group>
              <List size="sm" spacing={6}>{d.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
            </Paper>
          </Grid.Col>
        </Grid>
      )}
    </Stack>
  );
}
```

- [ ] **Step 2: MatchPage.tsx 全檔重寫**（分數大字級 teal）

```tsx
import { Button, Group, List, Paper, Progress, Stack, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getResume, matchJob, type MatchResult } from "./api";
import { PageHeader } from "./ui";

export default function MatchPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);

  async function run() {
    setErr(null);
    setResult(null);
    setBusy(true);
    const r = await matchJob(url.trim());
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "比對失敗");
      return;
    }
    setResult(await r.json());
  }

  return (
    <Stack p={36} maw={860}>
      <PageHeader title="JD 比對" subtitle="貼上 104 職缺網址，對你的履歷算吻合度與缺口" />
      {!resume.data?.has_resume && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷。</Text>}
      <Group wrap="nowrap">
        <TextInput
          style={{ flex: 1 }}
          placeholder="https://www.104.com.tw/job/xxxxx"
          value={url}
          onChange={(e) => setUrl(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
        />
        <Button onClick={run} loading={busy} disabled={!resume.data?.has_resume || !url.trim()}>比對</Button>
      </Group>
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {result && (
        <Paper bg="dark.6" radius="md" p="lg" mt="md">
          <Text fw={600} mb={4}>{result.title}
            <Text span c="dimmed" size="sm"> · {result.company} · {result.salary}</Text>
          </Text>
          <Group align="baseline" gap={8} my="sm">
            <Text c="teal.5" style={{
              fontFamily: "'Space Grotesk', sans-serif", fontSize: 44, fontWeight: 700,
              letterSpacing: "-2px", lineHeight: 1,
            }}>{result.score}</Text>
            <Text c="dimmed" size="sm">/ 100 吻合度</Text>
          </Group>
          <Progress value={result.score} color="teal" mb="md" />
          <Text size="sm" fw={600} mb={4}>契合理由</Text>
          <List size="sm" spacing={4} mb="md">{result.reasons.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
          <Text size="sm" fw={600} mb={4}>缺少技能 / 待補強</Text>
          <List size="sm" spacing={4}>{result.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
        </Paper>
      )}
    </Stack>
  );
}
```

- [ ] **Step 3: build 驗證**

Run: `npm run build`
Expected: 零 TS 錯誤

- [ ] **Step 4: Commit**

```bash
git add src/ResumePage.tsx src/MatchPage.tsx
git commit -m "feat(sentinel): 履歷健檢/JD比對頁重整——PageHeader+扁平面板+雙欄診斷（SP-UIUX）"
```

---

### Task 5: 推薦 + 職缺搜尋 + JobRow 重整

**Files:**
- Modify: `sentinel/web/frontend/src/JobRow.tsx`（全檔重寫）
- Modify: `sentinel/web/frontend/src/RecommendPage.tsx`（全檔重寫）
- Modify: `sentinel/web/frontend/src/SearchPage.tsx`（全檔重寫）

**Interfaces:**
- Consumes: `PageHeader`；`JobRow` props 介面不變（`{job: RecommendedJob; canMatch: boolean}`）。

- [ ] **Step 1: JobRow.tsx 全檔重寫**

```tsx
import { Anchor, Button, Group, List, Paper, Progress, Stack, Text } from "@mantine/core";
import { IconStarFilled } from "@tabler/icons-react";
import { useState } from "react";
import { matchJob, type MatchResult, type RecommendedJob } from "./api";

export default function JobRow({ job, canMatch }: { job: RecommendedJob; canMatch: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);

  async function run() {
    setErr(null);
    setBusy(true);
    const r = await matchJob(job.url);
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "比對失敗");
      return;
    }
    setResult(await r.json());
  }

  return (
    <Paper bg="dark.6" radius="md" px="md" py={12}>
      <Group justify="space-between" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            {job.is_watched && (
              <IconStarFilled size={12} style={{ color: "var(--mantine-color-tangerine-5)", flexShrink: 0 }} />
            )}
            <Text fw={600} size="sm" truncate>{job.title}</Text>
          </Group>
          <Text size="xs" c="dimmed">{job.company} · <Text span c="teal.5" ff="monospace">{job.salary}</Text></Text>
        </div>
        <Group gap="sm" wrap="nowrap">
          <Anchor href={job.url} target="_blank" size="xs" c="dimmed">去 104 看</Anchor>
          <Button size="compact-sm" variant="light" onClick={run} loading={busy} disabled={!canMatch}>比對</Button>
        </Group>
      </Group>
      {err && <Text c="danger.6" size="sm" mt="xs">{err}</Text>}
      {result && (
        <Stack gap={6} mt="sm">
          <Group align="baseline" gap={6}>
            <Text c="teal.5" fw={700} ff="'Space Grotesk', sans-serif" size="xl">{result.score}</Text>
            <Text c="dimmed" size="xs">/ 100</Text>
          </Group>
          <Progress value={result.score} color="teal" size="sm" />
          <Text size="xs" fw={600}>契合理由</Text>
          <List size="xs" spacing={2}>{result.reasons.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
          <Text size="xs" fw={600}>缺少技能 / 待補強</Text>
          <List size="xs" spacing={2}>{result.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
        </Stack>
      )}
    </Paper>
  );
}
```

- [ ] **Step 2: RecommendPage.tsx 全檔重寫**

```tsx
import { Button, Stack, Text } from "@mantine/core";
import { IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getRecommend, getResume, type RecommendedJob } from "./api";
import JobRow from "./JobRow";
import { PageHeader } from "./ui";

export default function RecommendPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [jobs, setJobs] = useState<RecommendedJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canMatch = !!resume.data?.has_resume;

  async function pull() {
    setErr(null);
    setBusy(true);
    const r = await getRecommend();
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "拉取推薦失敗");
      return;
    }
    setJobs((await r.json()).jobs);
  }

  return (
    <Stack p={36} maw={860}>
      <PageHeader
        title="推薦職缺"
        subtitle="拉取 104 個人化推薦，逐筆對履歷比對"
        action={
          <Button leftSection={<IconSparkles size={16} />} onClick={pull} loading={busy}>
            {busy ? "正在開啟瀏覽器拉取…" : "拉取推薦"}
          </Button>
        }
      />
      {!canMatch && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {jobs && jobs.length === 0 && <Text c="dimmed" size="sm">目前沒有推薦職缺。</Text>}
      <Stack gap={6}>
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
    </Stack>
  );
}
```

- [ ] **Step 3: SearchPage.tsx 全檔重寫**

```tsx
import { Button, Group, Stack, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getResume, getSettings, searchJobs, type RecommendedJob } from "./api";
import JobRow from "./JobRow";
import { PageHeader } from "./ui";

export default function SearchPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [kw, setKw] = useState("");
  const [jobs, setJobs] = useState<RecommendedJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [seeded, setSeeded] = useState(false);
  const canMatch = !!resume.data?.has_resume;

  // 首次載入把關注關鍵字帶入搜尋框（只 seed 一次，不覆寫使用者編輯中）
  useEffect(() => {
    if (!seeded && settings.data) {
      setKw((settings.data.watched_keywords ?? []).join(" "));
      setSeeded(true);
    }
  }, [seeded, settings.data]);

  async function run() {
    if (!kw.trim()) return;
    setErr(null);
    setBusy(true);
    const r = await searchJobs(kw.trim());
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "搜尋失敗");
      return;
    }
    setJobs((await r.json()).jobs);
  }

  return (
    <Stack p={36} maw={860}>
      <PageHeader title="職缺搜尋" subtitle="104 站內關鍵字搜尋，逐筆對履歷比對" />
      {!canMatch && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      <Group wrap="nowrap">
        <TextInput
          style={{ flex: 1 }}
          leftSection={<IconSearch size={15} />}
          placeholder="輸入關鍵字，如 Python 後端"
          value={kw}
          onChange={(e) => setKw(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
        />
        <Button onClick={run} loading={busy} disabled={!kw.trim()}>搜尋</Button>
      </Group>
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {jobs && jobs.length === 0 && <Text c="dimmed" size="sm">找不到符合的職缺。</Text>}
      <Stack gap={6}>
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
    </Stack>
  );
}
```

- [ ] **Step 4: build 驗證**

Run: `npm run build`
Expected: 零 TS 錯誤

- [ ] **Step 5: Commit**

```bash
git add src/JobRow.tsx src/RecommendPage.tsx src/SearchPage.tsx
git commit -m "feat(sentinel): 推薦/搜尋/JobRow 重整——扁平列+訊號色（SP-UIUX）"
```

---

### Task 6: 整理助手重整（配色對齊 + icon 替換）

**Files:**
- Modify: `sentinel/web/frontend/src/ChatPage.tsx`（局部改寫，邏輯不動）

**Interfaces:**
- Consumes: theme 色、Tabler icons。串流/套用/memory 全部邏輯保持原樣。

- [ ] **Step 1: import 區改寫**（檔頭 imports 改為）

```tsx
import {
  ActionIcon, Alert, Badge, Button, Group, Loader, Paper, ScrollArea,
  Stack, Text, TextInput, TypographyStylesProvider,
} from "@mantine/core";
import {
  IconBrain, IconDownload, IconEraser, IconTrash, IconX,
} from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./chat-md.css";
import {
  applyUpdate, clearChat, deleteMemory, getChat, readSse, sendChat, SuggestedUpdate,
} from "./api";
import { PageHeader } from "./ui";
```

（原本 import 的 `Card`、`Title` 若在下方步驟改寫後不再使用，一併自 import 移除。）

- [ ] **Step 2: SuggestionCard 外殼換扁平面板**（`<Card withBorder padding="xs" radius="md">`…`</Card>` 改為）

```tsx
    <Paper bg="dark.6" radius="md" px="md" py="xs">
      {/* 原 Card 內部內容原封不動 */}
    </Paper>
```

- [ ] **Step 3: 主排版改寫**（`return (` 內的最外層與訊息渲染，改為以下結構；`send/clear/removeFact/useEffect` 等邏輯完全不動）

```tsx
  return (
    <Group align="flex-start" p={36} gap="xl" wrap="nowrap">
      <Stack style={{ flex: 1, minWidth: 0 }} gap="sm">
        <PageHeader title="整理助手" subtitle="邊聊邊整理履歷與求職偏好；更新建議需按「套用」才會寫入" />
        <ScrollArea h={480} viewportRef={viewport} type="auto">
          <Stack gap="md" pr="sm">
            {msgs.map((m, i) => (
              <Stack key={i} gap={6} align={m.role === "user" ? "flex-end" : "flex-start"}>
                {m.role === "user" ? (
                  <Paper bg="dark.5" px="md" py="sm" radius="md" maw="85%">
                    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{m.content}</Text>
                  </Paper>
                ) : (
                  <div style={{ maxWidth: "92%" }}>
                    <TypographyStylesProvider fz="sm" className="chat-md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </TypographyStylesProvider>
                    {busy && i === msgs.length - 1 && <Loader size="xs" mt={4} />}
                    {m.interrupted && <Text size="xs" c="danger.6">回覆中斷</Text>}
                  </div>
                )}
                {m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}
                {m.remembered?.map((f, j) => (
                  <Badge key={j} variant="light" color="grape" leftSection={<IconBrain size={12} />}>
                    已記住：{f}
                  </Badge>
                ))}
                {m.forgot?.map((f, j) => (
                  <Badge key={j} variant="light" color="gray" leftSection={<IconEraser size={12} />}>
                    已忘記：{f}
                  </Badge>
                ))}
              </Stack>
            ))}
            {msgs.length === 0 && (
              <Alert color="gray" variant="light">
                跟我聊聊你的履歷或求職想法，例如「期望薪資改 9 萬」「我只想找雙北的工作」。
              </Alert>
            )}
          </Stack>
        </ScrollArea>
        <Group wrap="nowrap">
          <TextInput
            style={{ flex: 1 }}
            placeholder="輸入訊息，Enter 送出"
            value={input}
            onChange={(e) => setInput(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            disabled={busy}
          />
          <Button onClick={send} loading={busy}>送出</Button>
        </Group>
      </Stack>
      <Paper bg="dark.6" radius="md" p="md" w={280} style={{ flexShrink: 0 }}>
        <Group justify="space-between" mb="sm">
          <Group gap={6}>
            <IconBrain size={15} style={{ color: "var(--mantine-color-grape-4)" }} />
            <Text size="sm" fw={600}>半永久記憶</Text>
          </Group>
          <Group gap={2}>
            <ActionIcon variant="subtle" color="gray" size="sm" component="a" href="/api/export" title="匯出求職檔案 MD">
              <IconDownload size={14} />
            </ActionIcon>
            <ActionIcon variant="subtle" color="red" size="sm" onClick={clear} title="清空對話（記憶不清）">
              <IconTrash size={14} />
            </ActionIcon>
          </Group>
        </Group>
        <Stack gap={6}>
          {(history.data?.memory ?? []).map((f, i) => (
            <Group key={i} justify="space-between" wrap="nowrap" gap={4}>
              <Text size="xs" style={{ flex: 1 }}>{f.text}</Text>
              <ActionIcon size="xs" variant="subtle" color="red" onClick={() => removeFact(i)}>
                <IconX size={11} />
              </ActionIcon>
            </Group>
          ))}
          {(history.data?.memory ?? []).length === 0 && (
            <Text size="xs" c="dimmed">（尚無記憶——聊天中提到的長期偏好會自動記在這）</Text>
          )}
        </Stack>
      </Paper>
    </Group>
  );
```

注意：`clear()` 內 `window.confirm("確定清空對話？（半永久記憶不會清除）")` 保持不變；匯出/清空從文字按鈕改 icon 按鈕（`title` 屬性提供輔助文字）。

- [ ] **Step 4: chat-md.css 微調**（檔尾追加——助手訊息無底色後，收斂與使用者氣泡的視覺差）

```css
.mantine-TypographyStylesProvider-root.chat-md {
  color: var(--mantine-color-dark-1);
}
```

- [ ] **Step 5: build 驗證**

Run: `npm run build`
Expected: 零 TS 錯誤（未使用 import 需清乾淨）

- [ ] **Step 6: Commit**

```bash
git add src/ChatPage.tsx src/chat-md.css
git commit -m "feat(sentinel): 整理助手重整——氣泡配色+icon 徽章+側欄面板（SP-UIUX）"
```

---

### Task 7: 後端不動確認 + 真機驗收 + 收尾

**Files:**
- Modify: `docs/superpowers/career-sentinel-roadmap.md`

- [ ] **Step 1: 後端零變動確認**

Run: `git diff main..HEAD --stat -- sentinel/src/` → Expected: 空（本 SP 無後端 diff）
Run: `cd sentinel && uv run pytest -q` → Expected: `191 passed`

- [ ] **Step 2: 真機驗收（需使用者操作）**

`career-sentinel serve` → Ctrl+F5：
1. 側欄六項導覽、active 狀態、SENTINEL_ 字標、底部「重新抓取」可跨頁按、上次時間正確
2. 儀表板：大字級 KPI（含 +N teal／邀約 amber）、面試列＋日曆 icon、扁平清單 hover、彙整
3. 履歷健檢診斷雙欄、JD 比對大分數、推薦/搜尋 JobRow、聊天串流/套用/記憶/匯出 icon
4. 聊天中切頁再切回：訊息與狀態仍在
5. 設定 modal、到點提醒橫幅（可把 notify_time 設近測）

- [ ] **Step 3: roadmap 收尾 + Commit**

`docs/superpowers/career-sentinel-roadmap.md`：✅ 區加 SP-UIUX 條目（視覺方向、側欄、六頁重整、icon 替換）、劃掉技術債「SP1 儀表板視覺對齊 Cockpit」、更新日期。

```bash
git add docs/superpowers/career-sentinel-roadmap.md
git commit -m "docs(sentinel): UI/UX 改版完成（roadmap 收尾）"
```
