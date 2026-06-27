import { Anchor, Badge, Box, Button, Group, Stack, Text, Title } from "@mantine/core";
import { IconCoffee } from "../components/icons";
import { Link } from "react-router-dom";
import { Footer } from "../components/Footer";

// TODO: 開好贊助平台帳號後換成實際連結（綠界 ECPay / Portaly / GitHub Sponsors）
const DONATE_URL = "#";

const SKILLS = [
  "AI Native", "AI Builder",
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
