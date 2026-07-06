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
