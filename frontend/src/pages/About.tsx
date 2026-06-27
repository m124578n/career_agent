import { Anchor, Badge, Box, Button, Group, Stack, Text, Title } from "@mantine/core";
import { IconCoffee } from "../components/icons";
import { Link } from "react-router-dom";
import { Footer } from "../components/Footer";

// TODO: 開好贊助平台帳號後換成實際連結（綠界 ECPay / Portaly / GitHub Sponsors）
const DONATE_URL = "#";

const STATS: { value: string; label: string }[] = [
  { value: "7,000+", label: "服務使用者" },
  { value: "1,100+", label: "產出影片" },
  { value: "↓50%", label: "營運成本" },
  { value: "30%→<1%", label: "失敗率" },
];

const WORK: { role: string; org: string; period: string; items: string[] }[] = [
  {
    role: "Software Engineer",
    org: "Osense Technology",
    period: "2024 – 2025",
    items: [
      "主導 OVideo——AI 內容轉影片平台（1,800+ 使用者）：整合 GPT-4 / Claude / Gemini 做內容分析、腳本生成與圖文配對，並以 FFmpeg 處理影片編碼與字幕。",
      "效能與成本優化：影片生成時間 30→15 分鐘、月成本 $40K→$20K、以 Serverless 架構把並發從 10 擴展到 100+。",
      "打造 Osense AI——LINE 上的 AI 虛擬人與語音克隆系統（5,400+ 使用者）：整合 lip-sync 與 voice cloning，將失敗率從 30% 降到 <1%。",
      "導入 Clean Architecture 與設計模式，新功能開發時間 ↓50%；設計 PostgreSQL / MongoDB schema 支援高並發。",
    ],
  },
  {
    role: "Software Engineer",
    org: "Jung Shing International",
    period: "2022 – 2024",
    items: [
      "開發 Django 內部系統與網路爬蟲解決方案。",
    ],
  },
];

const SKILLS = [
  "AI Native", "AI Builder",
  "Python", "FastAPI", "Django", "Celery", "asyncio",
  "LLM 整合", "Prompt Engineering", "RAG", "FFmpeg", "Voice Cloning",
  "PostgreSQL", "MongoDB", "Redis", "Docker", "Azure", "Clean Architecture",
];

const LANGUAGES: { lang: string; level: string }[] = [
  { lang: "中文", level: "母語" },
  { lang: "日文", level: "JLPT N1" },
  { lang: "英文", level: "技術文件閱讀" },
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
          <Link to="/" className="jt-brand" style={{ textDecoration: "none" }}>
            JobTracker<span className="dot">.</span>
          </Link>
          <Anchor component={Link} to="/" c="dimmed" fz="sm">
            ← 回首頁
          </Anchor>
        </Group>

        <div className="jt-panel">
          <div className="jt-panel-body">
            <Stack gap={6} mb={18}>
              <span className="jt-eyebrow">關於我</span>
              <Title order={1} fz={{ base: 26, md: 32 }} fw={700} lts="-0.02em">
                詹舜智
              </Title>
              <Text c="dimmed" fz="sm">
                AI Application Engineer · Python Backend Specialist
              </Text>
            </Stack>

            <Text fz="sm" style={{ lineHeight: 1.8 }} mb={24}>
              我是詹舜智，AI Application Engineer／Python 後端工程師，有 3.5 年經驗，
              專長是把 LLM 與多模態 AI 整合進真正能上線的產品。曾從零打造 2 個 AI
              影音生成產品，累計服務 7,000+ 使用者、產出 1,100+ 支影片。擅長 LLM 整合、
              系統與成本優化（月成本 $40K→$20K）、以及可擴展的後端架構設計。日文 JLPT
              N1，能直接與日本團隊協作。期待打造對使用者真正有用的 AI 產品。
            </Text>

            {/* 經歷亮點 */}
            <div className="jt-eyebrow" style={{ marginBottom: 10 }}>經歷亮點</div>
            <Group gap={10} mb={24}>
              {STATS.map((s) => (
                <div
                  key={s.label}
                  style={{
                    flex: "1 1 110px",
                    minWidth: 110,
                    border: "1px solid var(--jt-border)",
                    borderRadius: "var(--jt-radius)",
                    background: "rgba(255,255,255,0.012)",
                    padding: "12px 14px",
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--mantine-font-family-monospace)",
                      fontSize: 20,
                      fontWeight: 600,
                      color: "var(--jt-teal)",
                      lineHeight: 1.1,
                    }}
                  >
                    {s.value}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--jt-dim)", marginTop: 4 }}>
                    {s.label}
                  </div>
                </div>
              ))}
            </Group>

            {/* 代表作 / 經歷 */}
            <div className="jt-eyebrow" style={{ marginBottom: 10 }}>代表作 / 經歷</div>
            <Stack gap={18} mb={24}>
              {WORK.map((w) => (
                <div key={`${w.org}-${w.period}`}>
                  <Group justify="space-between" wrap="nowrap" mb={6}>
                    <Text fz="sm" fw={600} c="var(--jt-text)">
                      {w.role} · {w.org}
                    </Text>
                    <Text
                      fz="xs"
                      c="dimmed"
                      style={{ fontFamily: "var(--mantine-font-family-monospace)", whiteSpace: "nowrap" }}
                    >
                      {w.period}
                    </Text>
                  </Group>
                  <Stack gap={8}>
                    {w.items.map((it, i) => (
                      <Group key={i} gap={10} wrap="nowrap" align="flex-start">
                        <span
                          aria-hidden
                          style={{
                            flexShrink: 0,
                            width: 6,
                            height: 6,
                            borderRadius: 99,
                            background: "var(--jt-teal)",
                            marginTop: 7,
                          }}
                        />
                        <Text fz="sm" c="var(--jt-muted)" style={{ lineHeight: 1.6 }}>
                          {it}
                        </Text>
                      </Group>
                    ))}
                  </Stack>
                </div>
              ))}
            </Stack>

            {/* 社群貢獻 */}
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>社群貢獻</div>
            <Text fz="sm" c="var(--jt-muted)" style={{ lineHeight: 1.7 }} mb={24}>
              iThome 鐵人賽 2023：發表 30 天「Django 原始碼解析」系列，深入 ORM、
              Middleware 與請求處理流程；並在個人部落格分享 Python 後端、AI 應用與系統設計。
            </Text>

            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>技能</div>
            <Group gap={8} mb={24}>
              {SKILLS.map((s) => (
                <Badge key={s} variant="default" radius="sm">{s}</Badge>
              ))}
            </Group>

            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>語言</div>
            <Stack gap={8} mb={24}>
              {LANGUAGES.map((l) => (
                <Group key={l.lang} gap={10} wrap="nowrap">
                  <Text fz="xs" c="dimmed" style={{ minWidth: 72 }}>{l.lang}</Text>
                  <Text fz="sm" c="var(--jt-muted)">{l.level}</Text>
                </Group>
              ))}
            </Stack>

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

            <div className="jt-eyebrow" style={{ margin: "22px 0 8px" }}>支持我</div>
            <Stack gap={8}>
              <Text fz="sm" c="dimmed">
                覺得這個工具有幫助嗎？歡迎請我喝杯咖啡。
              </Text>
              <Button
                component="a"
                href={DONATE_URL}
                target="_blank"
                rel="noreferrer"
                color="tangerine"
                radius="sm"
                w="fit-content"
                leftSection={<IconCoffee size={16} />}
              >
                請我喝咖啡
              </Button>
            </Stack>
          </div>
        </div>
      </Box>
      <Footer />
    </Box>
  );
}
