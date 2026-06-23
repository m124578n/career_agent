# 關於我頁面 + 公開存取 + 全站 footer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增公開的「關於我」頁（自介 + 6 聯繫渠道）、側欄導航項、與全站版權 footer，並把前端路由重構成「公開 /about + 其餘需登入」。

**Architecture:** 路由集中到 `main.tsx`，用 react-router layout route（`<Outlet/>`）：`/about` 為公開頁、其餘子路由包在 `<AuthGate>` + `ResumeProvider` + AppShell layout（由 `App` 改成的 `GatedLayout`）下。新增 `About` 頁與共用 `Footer` 元件。

**Tech Stack:** React + react-router-dom v7（layout route + Outlet）、Mantine、TypeScript（型別 gate `tsc --noEmit`）。

## Global Constraints

- 前端無單元測試框架；型別 gate `frontend/node_modules/.bin/tsc.cmd --noEmit`（exit 0）
- 不接後端、不存 DB（純前端靜態頁）
- 沿用 `jt-` 風格與既有元件慣例
- `/about` 公開（登入前後皆可達）；其餘路由維持 `AuthGate` 攔截
- `ResumeProvider` 必須留在 `AuthGate` 內（登入後才掛）
- 聯繫渠道與連結（逐字）：
  - Email `mailto:m23568n@gmail.com`
  - GitHub `https://github.com/m124578n`
  - LinkedIn `https://www.linkedin.com/in/john19980215`
  - Medium `https://medium.com/@m23568n`
  - dev.to `https://dev.to/shunchih`
  - 個人網站 `https://m124578n.github.io/`
- 版權字串：`© 2026 詹舜智 · JobTracker`
- 名字/頭銜：詹舜智 · Python Backend & AI Application Engineer
- 外部連結一律 `target="_blank" rel="noreferrer"`
- commit 不加 `--no-verify`

---

### Task 1: Footer 共用元件

**Files:**
- Create: `frontend/src/components/Footer.tsx`

**Interfaces:**
- Produces: `export function Footer(): JSX.Element` — 一行置中版權列，含 GitHub 連結

- [ ] **Step 1: 建 `frontend/src/components/Footer.tsx`**

```tsx
export function Footer() {
  return (
    <div
      style={{
        textAlign: "center",
        fontSize: 12,
        color: "var(--jt-dim)",
        padding: "16px 0",
      }}
    >
      © 2026 詹舜智 · JobTracker ·{" "}
      <a
        href="https://github.com/m124578n"
        target="_blank"
        rel="noreferrer"
        style={{ color: "var(--jt-dim)" }}
      >
        GitHub
      </a>
    </div>
  );
}
```

- [ ] **Step 2: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/Footer.tsx
git commit -m "feat(fe): 加共用 Footer 版權元件"
```

---

### Task 2: About 公開頁

**Files:**
- Create: `frontend/src/pages/About.tsx`

**Interfaces:**
- Consumes: Task 1 `Footer`
- Produces: `export function About(): JSX.Element` — 自包含 layout（不依賴 AppShell）的名片式公開頁

- [ ] **Step 1: 建 `frontend/src/pages/About.tsx`**

```tsx
import { Anchor, Badge, Box, Group, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";
import { Footer } from "../components/Footer";

const SKILLS = [
  "Python", "FastAPI", "Django", "LLM 整合",
  "Prompt Engineering", "RAG", "Docker", "Azure",
];

const CONTACTS: { label: string; href: string }[] = [
  { label: "Email", href: "mailto:m23568n@gmail.com" },
  { label: "GitHub", href: "https://github.com/m124578n" },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/john19980215" },
  { label: "Medium", href: "https://medium.com/@m23568n" },
  { label: "dev.to", href: "https://dev.to/shunchih" },
  { label: "個人網站", href: "https://m124578n.github.io/" },
];

export function About() {
  return (
    <Box
      style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}
    >
      <Box p={{ base: "lg", md: 40 }} maw={720} mx="auto" w="100%" style={{ flex: 1 }}>
        <Group justify="space-between" mb={24}>
          <span className="jt-brand">
            JobTracker<span className="dot">.</span>
          </span>
          <Anchor component={Link} to="/" c="dimmed" fz="sm">
            ← 回首頁
          </Anchor>
        </Group>

        <div className="jt-panel">
          <div className="jt-panel-body">
            <Stack gap={6} mb={18}>
              <span className="jt-eyebrow">關於我 // ABOUT</span>
              <Title order={1} fz={{ base: 26, md: 32 }} fw={700} lts="-0.02em">
                詹舜智
              </Title>
              <Text c="dimmed" fz="sm">
                Python Backend &amp; AI Application Engineer
              </Text>
            </Stack>

            <Text fz="sm" style={{ lineHeight: 1.8 }} mb={20}>
              我是詹舜智，有 3.5 年 Python 後端開發經驗，專注於把 LLM 與 AI
              應用整合進產品。曾在 Osense Technology 主導 AI 影片生成平台
              OVideo，從零設計整條 pipeline、整合 GPT-4 / Claude / Gemini
              等模型，並透過架構優化把營運成本減半、並發處理量擴展到 10
              倍以上。熟悉 FastAPI 與 Django（曾在 iThome 鐵人賽發表 30
              篇 Django 原始碼解析）。現階段以 Azure 雲端服務為主，投入
              雲端架構與產品設計相關的工作，期待打造對使用者真正有用的 AI 產品。
            </Text>

            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>技能</div>
            <Group gap={8} mb={22}>
              {SKILLS.map((s) => (
                <Badge key={s} variant="default" radius="sm">{s}</Badge>
              ))}
            </Group>

            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>聯繫方式</div>
            <Stack gap={8}>
              {CONTACTS.map((c) => (
                <Group key={c.label} gap={10} wrap="nowrap">
                  <Text fz="xs" c="dimmed" style={{ minWidth: 72 }}>{c.label}</Text>
                  <Anchor href={c.href} target="_blank" rel="noreferrer" fz="sm">
                    {c.href.replace(/^mailto:/, "")}
                  </Anchor>
                </Group>
              ))}
            </Stack>
          </div>
        </div>
      </Box>
      <Footer />
    </Box>
  );
}
```

- [ ] **Step 2: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/About.tsx
git commit -m "feat(fe): 加關於我公開頁（名片式 + 6 聯繫渠道）"
```

---

### Task 3: 路由重構 + App 改 layout + 側欄導航/footer

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: Task 2 `About`、Task 1 `Footer`
- Produces: `App` 改名導出為 `GatedLayout`（AppShell layout + `<Outlet/>`）；`main.tsx` 集中路由，`/about` 公開

- [ ] **Step 1: 把 `App.tsx` 從「含內部 Routes」改成 layout 元件**

把 `App.tsx` 上半段（import 與 `export function App`）改為：移除 `Routes/Route/Navigate` 與頁面元件 import（移到 main），改 import `Outlet`，加 `Footer`，把 `App` 改名 `GatedLayout`、`NAV` 加關於我、側欄底加 `Footer`、Main 用 `<Outlet/>`。

將檔案開頭到 `export function App()` 的 `return (...)` 結束（即 `AppShell` 整段）替換為：

```tsx
import { Anchor, AppShell, Avatar, Group, NavLink, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { Outlet, NavLink as RouterNavLink } from "react-router-dom";
import { api } from "./api/client";
import { useAuth } from "./state/auth";
import { Footer } from "./components/Footer";

const NAV = [
  { to: "/resume", label: "履歷與目標", tag: "01" },
  { to: "/jobs", label: "職缺契合度", tag: "02" },
  { to: "/applications", label: "追蹤清單", tag: "03" },
  { to: "/about", label: "關於我", tag: "04" },
];

export function GatedLayout() {
  return (
    <AppShell navbar={{ width: 232, breakpoint: "sm" }} padding={0}>
      <AppShell.Navbar
        p="md"
        style={{
          background: "var(--jt-panel)",
          borderColor: "var(--jt-border)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Stack gap={2} mb="xl" px={6} pt={4}>
          <span className="jt-brand">
            JobTracker<span className="dot">.</span>
          </span>
          <span className="jt-brandtag">AI 求職指揮艙</span>
        </Stack>

        <Stack gap={4}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              component={RouterNavLink}
              to={item.to}
              label={item.label}
              leftSection={
                <span
                  style={{
                    fontFamily: "var(--mantine-font-family-monospace)",
                    fontSize: 11,
                    color: "var(--jt-dim)",
                  }}
                >
                  {item.tag}
                </span>
              }
              styles={{
                root: { borderRadius: 8 },
                label: { fontSize: 14, fontWeight: 500 },
              }}
            />
          ))}
        </Stack>

        <div style={{ marginTop: "auto" }}>
          <AccountFooter />
          <Footer />
        </div>
      </AppShell.Navbar>

      <AppShell.Main style={{ minHeight: "100dvh" }}>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
```

說明：這段從**檔案第 1 行的 import 區**一路替換到原 `export function App() { ... }` 函式的結尾 `}`。上面的 import 區已是**完整版**——保留了 `AccountFooter` 需要的 `Anchor/Avatar/Group/Text/useQuery/api/useAuth`，新增 `Outlet/Footer`，移除了只有舊 `App` 用到的 `Navigate/Route/Routes` 與頁面元件（`ResumeSetup/JobList/Applications`）import。`AccountFooter` 元件定義（位於原 `App` 函式**之後**）與其餘既有程式碼保持不動。

- [ ] **Step 2: 重寫 `main.tsx` 集中路由**

把 `main.tsx` 的 import 與 `gated` 整段改為：

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles/global.css";
import { GatedLayout } from "./App";
import { About } from "./pages/About";
import { ResumeSetup } from "./pages/ResumeSetup";
import { JobList } from "./pages/JobList";
import { Applications } from "./pages/Applications";
import { theme } from "./theme";
import { ResumeProvider } from "./state/resume";
import { AuthProvider } from "./state/auth";
import { AuthGate } from "./components/AuthGate";

const queryClient = new QueryClient();
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

function GatedShell() {
  return (
    <AuthGate>
      <ResumeProvider>
        <GatedLayout />
      </ResumeProvider>
    </AuthGate>
  );
}

const app = (
  <AuthProvider>
    <BrowserRouter>
      <Routes>
        <Route path="/about" element={<About />} />
        <Route element={<GatedShell />}>
          <Route path="/" element={<Navigate to="/resume" replace />} />
          <Route path="/resume" element={<ResumeSetup />} />
          <Route path="/jobs" element={<JobList />} />
          <Route path="/applications" element={<Applications />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </AuthProvider>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark" forceColorScheme="dark">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        {GOOGLE_CLIENT_ID ? (
          <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{app}</GoogleOAuthProvider>
        ) : (
          app
        )}
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 3: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0（特別注意：`App.tsx` 不再 import 未使用的 `Navigate/Route/Routes` 與頁面元件，否則 TS6133 未使用報錯）

- [ ] **Step 4: 手動驗證（前端 dev server 已在跑）**

- **未登入**直接開 `/about` → 看得到關於我頁（公開）。
- 登入後從側欄「04 關於我」→ 進 `/about`。
- 其餘路由（/resume、/jobs、/applications）登入後正常；登入後直接開深層路徑（如 /jobs）不會壞。
- 未登入開 `/jobs` → 仍被 `AuthGate` 攔到登入畫面。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat(fe): 路由重構，/about 公開、側欄加關於我與 footer"
```

---

### Task 4: 登入頁加 Footer

**Files:**
- Modify: `frontend/src/components/LoginScreen.tsx`

**Interfaces:**
- Consumes: Task 1 `Footer`

- [ ] **Step 1: LoginScreen 底部加 Footer**

`LoginScreen.tsx` import 加 `Footer`，並把最外層容器改成欄向、底部放 `Footer`。

把 `import { useAuth } ...` 後加：

```tsx
import { Footer } from "./Footer";
```

把最外層 `<div style={{ minHeight: "100dvh", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>` 改為包一層欄向容器，原置中卡片不動、底部加 Footer：

```tsx
  return (
    <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
        }}
      >
        <div
          className="jt-panel"
          style={{ padding: 40, maxWidth: 380, width: "100%", textAlign: "center" }}
        >
          <span className="jt-brand" style={{ fontSize: 22 }}>
            JobTracker<span className="dot">.</span>
          </span>
          <div className="jt-brandtag" style={{ marginTop: 8 }}>
            AI 求職指揮艙
          </div>
          <p style={{ color: "var(--jt-muted)", fontSize: 14, margin: "22px 0 20px" }}>
            用 Google 登入開始使用。
            <br />
            履歷診斷、職缺契合度、求職信 —— 每日有使用額度。
          </p>
          <div style={{ display: "flex", justifyContent: "center" }}>
            <GoogleLogin
              onSuccess={(r) => r.credential && login(r.credential)}
              onError={() => undefined}
              theme="filled_black"
              shape="pill"
            />
          </div>
        </div>
      </div>
      <Footer />
    </div>
  );
```

- [ ] **Step 2: 型別檢查**

Run: `cd frontend && ./node_modules/.bin/tsc.cmd --noEmit`
Expected: exit 0

- [ ] **Step 3: 手動驗證**

- 啟用登入時，登入畫面底部出現版權 footer。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/LoginScreen.tsx
git commit -m "feat(fe): 登入頁底加 footer"
```

---

## Self-Review 註記

- **Spec coverage**：Footer 元件(T1)、About 公開頁+6 渠道(T2)、公開路由架構+側欄 NAV+側欄 footer(T3)、登入頁 footer(T4) 皆有對應。三處 footer = About(T2)、側欄(T3)、登入頁(T4)。
- **路由方案**：採 layout route（`<Outlet/>`）取代 spec 的巢狀 Routes，避免 descendant `<Routes>` 的相對路徑坑；`ResumeProvider` 維持在 `AuthGate` 內（`GatedShell`）。
- **型別一致**：`GatedLayout`（App.tsx 導出）↔ main.tsx import 名稱一致；`About`、`Footer` 命名一致。
- **未使用 import**：T3 Step 3 明確提醒移除 `App.tsx` 不再用的 import，避免 TS6133。
- **連結逐字**：六個聯繫連結與版權字串與 Global Constraints 一致。
