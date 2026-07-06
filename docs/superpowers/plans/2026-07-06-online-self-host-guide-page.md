# 線上版「本機自架」介紹＋教學頁 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在線上版 `frontend/` 加一個公開頁 `/self-host`，介紹本機自架版 career-sentinel 並附完整啟動教學（安裝 → Azure AI Foundry Claude key 申請 → `.env` → 登入 104 → 啟動）。

**Architecture:** 純靜態內容頁，沿用 `frontend` 既有頁面慣例（`About.tsx` 的 `jt-panel`/`jt-eyebrow`、頂部 brand ＋「← 回首頁」、底部 `Footer`）。react-router 公開路由（`GatedShell` 外）＋ Landing 加一個 CTA 連結。無 API/state/auth。

**Tech Stack:** React + react-router-dom + Mantine 7（`@mantine/core` 的 `Code`/`Anchor`/`Title`/`Text`/`Stack`/`List`），部署 Cloudflare Pages。

## Global Constraints

- 目標 codebase＝`frontend/`（線上版），非 `sentinel/`。
- 公開頁（`GatedShell` 外），免登入可看。
- 視覺沿用 `frontend` 既有慣例（`jt-panel`/`jt-panel-body`/`jt-eyebrow`/`jt-brand`/Mantine/`Footer`），不引入新設計語言。
- key 教學**只涵蓋 Azure AI Foundry Claude Sonnet**（其他 provider 尚未可用）。
- 教學指令/env 必須與 `sentinel` 現況一致：`uv sync`、`uv run rebrowser_playwright install chromium`、`FOUNDRY_API_KEY`/`FOUNDRY_BASE_URL`/`FOUNDRY_MODEL`、`career-sentinel login`/`serve`/`run`。
- 驗證：`frontend/` 的 `npm run build` 必過；無單元測試（內容頁）。

## Azure AI Foundry 步驟（已 WebFetch 現行官方文件 2026-06-23，逐字用於內容）

- 需求：付費 Azure 訂閱（pay-as-you-go 有效付款）、對資源群組有 **Contributor/Owner**、可存取 **Azure Marketplace**、Foundry 專案在 **East US2** 或 **Sweden Central**（Claude 支援區）。
- 步驟：
  1. 登入 [Microsoft Foundry](https://ai.azure.com)，確認開啟 **New Foundry**。
  2. 建立 Foundry 專案，區域選 **East US2** 或 **Sweden Central**。
  3. 上方 **Discover** → 左側 **Models** → 選 **Claude Sonnet**（`claude-sonnet-4-6`）。
  4. **Deploy → Custom settings** → 讀並 **Agree and Proceed** 接受 Azure Marketplace 條款。
  5. 設定部署名（預設 `claude-sonnet-4-6`，之後當 `model` 用）、**Region scope: Global** → **Deploy**。
  6. 部署完成 → **Details** 分頁，複製 **Target URI** 與 **Key**。
- 對應 career-sentinel `.env`：
  - `FOUNDRY_API_KEY` = Details 的 **Key**。
  - `FOUNDRY_BASE_URL` = Target URI 去掉尾端 `/v1/messages`，即 `https://<資源名>.services.ai.azure.com/anthropic`。
  - `FOUNDRY_MODEL` = 部署名（預設 `claude-sonnet-4-6`）。

## File Structure

- Create: `frontend/src/pages/SelfHost.tsx` — 新頁（named export `SelfHost`），全部內容。
- Modify: `frontend/src/main.tsx` — 加 `lazy` import ＋ 公開路由 `/self-host`。
- Modify: `frontend/src/pages/Landing.tsx` — 頂部 Group 加一個導向 `/self-host` 的 CTA 連結。

---

### Task 1: SelfHost 頁 ＋ 路由 ＋ Landing 連結

**Files:**
- Create: `frontend/src/pages/SelfHost.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/pages/Landing.tsx`

**Interfaces:**
- Produces: `SelfHost`（named export，`() => JSX.Element`）；公開路由 `/self-host`。
- Consumes: 既有 CSS class `jt-panel`/`jt-panel-body`/`jt-eyebrow`/`jt-brand`、`Footer` 元件、Mantine 元件、react-router `Link`。

- [ ] **Step 1: 建立 `frontend/src/pages/SelfHost.tsx`（完整內容，逐字）**

```tsx
import { Anchor, Box, Code, Group, List, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";
import { Footer } from "../components/Footer";

const REPO = "https://github.com/m124578n/career_agent";

export function SelfHost() {
  return (
    <Box style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <Box p={{ base: "lg", md: 40 }} maw={780} mx="auto" w="100%" style={{ flex: 1 }}>
        <Group justify="space-between" mb={24}>
          <Link to="/" className="jt-brand" style={{ textDecoration: "none" }}>
            JobTracker<span className="dot" aria-hidden="true">.</span>
          </Link>
          <Anchor component={Link} to="/" c="dimmed" fz="sm">
            ← 回首頁
          </Anchor>
        </Group>

        {/* 介紹 */}
        <div className="jt-panel">
          <div className="jt-panel-body">
            <Stack gap={6} mb={16}>
              <span className="jt-eyebrow">本機自架版</span>
              <Title order={1} fz={{ base: 26, md: 32 }} fw={700} lts="-0.02em">
                career-sentinel — 你電腦上的 104 求職哨兵
              </Title>
              <Text c="dimmed" fz="sm">本機、單人、自帶 key。資料留在你電腦。</Text>
            </Stack>
            <Text fz="sm" style={{ lineHeight: 1.8 }} mb={12}>
              career-sentinel 是這個專案的「本機自架」版本：在你自己的電腦上跑，用你自己的
              瀏覽器登入態讀 104（誰看過我、投遞狀態、訊息、面試邀約），存成本機快照、跟上次
              比對變化、用 LLM 幫你彙整，還能跟「求職總指揮」聊天把整條求職流程做完。
            </Text>
            <Text fz="sm" style={{ lineHeight: 1.8 }} mb={12}>
              和這個線上版 JobTracker 的差別：線上版是雲端多人、Google 登入即用；自架版是本機
              單人、自己帶 LLM key，換來資料完全留在自己電腦、直接讀你的 104 登入態。它只讀取、
              不會代你投遞或寫入 104。
            </Text>
            <Text fz="sm">
              原始碼：{" "}
              <Anchor href={REPO} target="_blank" rel="noopener noreferrer">
                github.com/m124578n/career_agent
              </Anchor>
            </Text>
          </div>
        </div>

        {/* 需求 */}
        <div className="jt-panel" style={{ marginTop: 20 }}>
          <div className="jt-panel-body">
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>開始前你需要</div>
            <List size="sm" spacing={6}>
              <List.Item>Python 3.12 以上</List.Item>
              <List.Item><Anchor href="https://docs.astral.sh/uv/" target="_blank" rel="noopener noreferrer">uv</Anchor>（Python 套件/環境管理器）與 Git</List.Item>
              <List.Item>一個 104 帳號（你平常在用的）</List.Item>
              <List.Item>一組 Azure AI Foundry 的 Claude Sonnet key（下面第 2 步教你申請）</List.Item>
            </List>
          </div>
        </div>

        {/* 步驟 1：安裝 */}
        <div className="jt-panel" style={{ marginTop: 20 }}>
          <div className="jt-panel-body">
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>1 · 下載與安裝</div>
            <Text fz="sm" mb={8}>把專案抓下來，安裝相依與反偵測的瀏覽器驅動：</Text>
            <Code block>{`git clone https://github.com/m124578n/career_agent.git
cd career_agent/sentinel
uv sync
uv run rebrowser_playwright install chromium`}</Code>
            <Text fz="xs" c="dimmed" mt={8} style={{ lineHeight: 1.7 }}>
              最後一行安裝的是打過 patch 的 Chromium 驅動，用來自動通過 104 私人頁前的
              Cloudflare 人機驗證。
            </Text>
          </div>
        </div>

        {/* 步驟 2：Azure AI Foundry key */}
        <div className="jt-panel" style={{ marginTop: 20 }}>
          <div className="jt-panel-body">
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>2 · 申請 Azure AI Foundry 的 Claude Sonnet key</div>
            <Text fz="sm" mb={8} style={{ lineHeight: 1.8 }}>
              目前實際可用的 LLM 路徑是 Azure AI Foundry 上的 Claude Sonnet。需要一個有付款方式的
              付費 Azure 訂閱（pay-as-you-go），並對資源群組有 Contributor 或 Owner 權限。
            </Text>
            <List type="ordered" size="sm" spacing={6}>
              <List.Item>
                登入{" "}
                <Anchor href="https://ai.azure.com" target="_blank" rel="noopener noreferrer">Microsoft Foundry</Anchor>
                （ai.azure.com），確認右上角「New Foundry」為開啟。
              </List.Item>
              <List.Item>建立一個 Foundry 專案，區域選 <b>East US2</b> 或 <b>Sweden Central</b>（Claude 支援的部署區）。</List.Item>
              <List.Item>上方點 <b>Discover</b> → 左側 <b>Models</b> → 選 <b>Claude Sonnet</b>（模型 ID <Code>claude-sonnet-4-6</Code>）。</List.Item>
              <List.Item>按 <b>Deploy → Custom settings</b>，閱讀並 <b>Agree and Proceed</b> 接受 Azure Marketplace 條款。</List.Item>
              <List.Item>設定部署名稱（預設 <Code>claude-sonnet-4-6</Code>，之後會當成 model 名），Region scope 選 <b>Global</b>，按 <b>Deploy</b>。</List.Item>
              <List.Item>部署完成後開 <b>Details</b> 分頁，複製 <b>Target URI</b> 與 <b>Key</b> 兩個值。</List.Item>
            </List>
            <Text fz="xs" c="dimmed" mt={8} style={{ lineHeight: 1.7 }}>
              計費走 Azure Marketplace 的 Claude 用量。Base URL 就是 Target URI 去掉結尾的
              <Code>/v1/messages</Code>，也就是 <Code>https://&lt;資源名&gt;.services.ai.azure.com/anthropic</Code>。
            </Text>
          </div>
        </div>

        {/* 步驟 3：.env */}
        <div className="jt-panel" style={{ marginTop: 20 }}>
          <div className="jt-panel-body">
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>3 · 設定 .env</div>
            <Text fz="sm" mb={8}>複製範例檔後，填入上一步拿到的值：</Text>
            <Code block>{`cp .env.example .env`}</Code>
            <Text fz="sm" mt={10} mb={8}>把 .env 內容改成（用 Azure AI Foundry 的 Claude）：</Text>
            <Code block>{`FOUNDRY_API_KEY=你的-Foundry-Key
FOUNDRY_BASE_URL=https://<你的資源名>.services.ai.azure.com/anthropic
FOUNDRY_MODEL=claude-sonnet-4-6`}</Code>
            <Text fz="xs" c="dimmed" mt={8} style={{ lineHeight: 1.7 }}>
              有設 <Code>FOUNDRY_API_KEY</Code> 時，career-sentinel 會走 Foundry 這條路。
            </Text>
          </div>
        </div>

        {/* 步驟 4：登入 104 */}
        <div className="jt-panel" style={{ marginTop: 20 }}>
          <div className="jt-panel-body">
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>4 · 首次登入 104</div>
            <Text fz="sm" mb={8}>開一個專用的 Chrome 視窗手動登入 104（只存瀏覽器 profile、不存你的帳密）：</Text>
            <Code block>{`uv run career-sentinel login`}</Code>
          </div>
        </div>

        {/* 步驟 5：啟動 */}
        <div className="jt-panel" style={{ marginTop: 20 }}>
          <div className="jt-panel-body">
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>5 · 啟動</div>
            <Text fz="sm" mb={8}>啟動本機儀表板與「求職總指揮」聊天：</Text>
            <Code block>{`uv run career-sentinel serve`}</Code>
            <Text fz="sm" mt={10} style={{ lineHeight: 1.8 }}>
              然後用瀏覽器打開{" "}
              <Anchor href="http://127.0.0.1:8765" target="_blank" rel="noopener noreferrer">http://127.0.0.1:8765</Anchor>。
              也可以用 <Code>uv run career-sentinel run</Code> 只跑一次「擷取 → 比對 → 彙整」。
            </Text>
          </div>
        </div>

        {/* 注意事項 */}
        <div className="jt-panel" style={{ marginTop: 20 }}>
          <div className="jt-panel-body">
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>注意事項</div>
            <List size="sm" spacing={6}>
              <List.Item>104 私人頁在 Cloudflare 後面，首次或偶爾可能要在開啟的瀏覽器過一次人機驗證。</List.Item>
              <List.Item>資料存在 <Code>sentinel/data</Code>（可用環境變數 <Code>SENTINEL_DATA_DIR</Code> 覆寫）。</List.Item>
              <List.Item>agent 只讀取 104，不會代你投遞或寫入。</List.Item>
            </List>
          </div>
        </div>
      </Box>
      <Footer />
    </Box>
  );
}
```

- [ ] **Step 2: `frontend/src/main.tsx` 加 lazy import ＋ 公開路由**

在既有 `const About = lazy(...)` 那組 lazy 宣告後加：

```tsx
const SelfHost = lazy(() => import("./pages/SelfHost").then((m) => ({ default: m.SelfHost })));
```

在 `<Route path="/about" element={<About />} />` 之後（同為 `GatedShell` 外的公開路由）加：

```tsx
          <Route path="/self-host" element={<SelfHost />} />
```

- [ ] **Step 3: `frontend/src/pages/Landing.tsx` 頂部加 CTA 連結**

把頂部 Group 內既有的「關於作者 →」那段：

```tsx
        <Anchor component={Link} to="/about" c="dimmed" fz="sm">
          關於作者 →
        </Anchor>
```

改成兩個連結並排（新增「本機自架版 →」）：

```tsx
        <Group gap="lg">
          <Anchor component={Link} to="/self-host" c="dimmed" fz="sm">
            本機自架版 →
          </Anchor>
          <Anchor component={Link} to="/about" c="dimmed" fz="sm">
            關於作者 →
          </Anchor>
        </Group>
```

（`Group` 已在 Landing.tsx 的 `@mantine/core` import 內，無需改 import。）

- [ ] **Step 4: build 驗證**

Run: `cd frontend && npm run build`
Expected: 成功（`tsc` 無型別錯誤、`vite build` 完成；無未用 import）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SelfHost.tsx frontend/src/main.tsx frontend/src/pages/Landing.tsx
git commit -m "feat(online): 本機自架介紹+啟動教學頁 /self-host（Azure Foundry Claude key）"
```

---

## Self-Review

**Spec coverage：**
- 公開頁 `/self-host`（GatedShell 外）＋ lazy 掛載 → Step 1、2 ✅
- Landing CTA 連結 → Step 3 ✅
- 內容八區塊（介紹/需求/安裝/Azure key/​.env/登入104/啟動/注意）→ Step 1 全含 ✅
- key 段只教 Azure AI Foundry Claude Sonnet、含正確 endpoint/部署名/env 對應 → Step 1 第 2、3 區塊（Azure 步驟來自現行官方文件）✅
- 指令/env 與 sentinel 現況一致（uv sync、rebrowser install、FOUNDRY_*、login/serve/run）→ Step 1 ✅
- 視覺沿用 jt-panel/jt-eyebrow/Footer/brand → Step 1（mirror About.tsx）✅
- `npm run build` 驗證 → Step 4 ✅

**Placeholder scan：** 無 TBD/TODO；頁面內容完整、指令確切。（`你的-Foundry-Key`、`<你的資源名>` 是教學要使用者自填的示意值，非 plan placeholder。）

**Type consistency：** named export `SelfHost` 於 SelfHost.tsx 定義、main.tsx lazy import 一致；路由 `/self-host` 於 main.tsx 與 Landing 連結一致；`jt-panel`/`jt-panel-body`/`jt-eyebrow`/`jt-brand` 沿用 About.tsx 既有 class；Mantine `Code`/`List`/`Anchor`/`Group` 皆 `@mantine/core` 既有。
