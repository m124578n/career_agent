import { Anchor, Badge, Group, List, Paper, Stack, Text, Title } from "@mantine/core";
import { PageContainer, PageHeader } from "./ui";

const SKILLS = [
  "AI Native", "AI Builder", "Python", "FastAPI", "Django",
  "LLM 整合", "Prompt Engineering", "RAG", "Docker", "Azure",
];

const CONTACTS: { label: string; href: string }[] = [
  { label: "Email", href: "mailto:m23568n@gmail.com" },
  { label: "GitHub", href: "https://github.com/m124578n" },
  { label: "LinkedIn", href: "https://www.linkedin.com/in/john19980215" },
  { label: "Medium", href: "https://medium.com/@m23568n" },
  { label: "dev.to", href: "https://dev.to/shunchih" },
  { label: "個人網站", href: "https://m124578n.github.io/" },
];

export default function AboutPage() {
  return (
    <PageContainer size="md">
      <PageHeader title="關於" subtitle="career-sentinel 是什麼，以及作者" />
      <Stack gap="lg">
        <Paper bg="dark.6" radius="md" p="lg">
          <Title order={4} mb="sm">關於 career-sentinel</Title>
          <Text size="sm" c="dark.1" style={{ lineHeight: 1.8 }}>
            career-sentinel 是一個在你電腦本機執行的單人求職 agent，把整條求職流程串成「跟 agent 聊天就能做完」：
          </Text>
          <List size="sm" spacing={4} mt="sm">
            <List.Item>整理履歷與求職偏好（目標職稱、薪資、地點）</List.Item>
            <List.Item>找職缺、讀 JD、比對適合度</List.Item>
            <List.Item>客製化履歷與求職信、開 104 投遞頁</List.Item>
            <List.Item>追蹤誰看過我、面試邀約、投遞與 offer</List.Item>
            <List.Item>offer 並排比較、以及依市場行情給議價策略</List.Item>
          </List>
          <Text size="xs" c="dimmed" mt="md" style={{ lineHeight: 1.7 }}>
            本機執行、資料留在你電腦；讀 104 用你自己的登入態瀏覽器，agent 不代你投遞或寫入 104。
          </Text>
        </Paper>

        <Paper bg="dark.6" radius="md" p="lg">
          <Text size="xs" c="dimmed" mb={2} style={{ letterSpacing: 1 }}>關於作者</Text>
          <Title order={3} mb={2}>詹舜智</Title>
          <Text size="sm" c="dimmed" mb="md">Python Backend &amp; AI Application Engineer</Text>
          <Text size="sm" c="dark.1" style={{ lineHeight: 1.8 }}>
            有 3.5 年 Python 後端開發經驗，專注於把 LLM 與 AI 應用整合進產品。曾在 Osense Technology
            主導 AI 影片生成平台 OVideo，從零設計整條 pipeline、整合 GPT-4 / Claude / Gemini 等模型，
            並透過架構優化把營運成本減半、並發處理量擴展到 10 倍以上。熟悉 FastAPI 與 Django（曾在
            iThome 鐵人賽發表 30 篇 Django 原始碼解析）。現以 Azure 雲端服務為主，投入雲端架構與產品
            設計，期待打造對使用者真正有用的 AI 產品。
          </Text>

          <Text size="xs" c="dimmed" mt="lg" mb={6} style={{ letterSpacing: 1 }}>技能</Text>
          <Group gap={8}>
            {SKILLS.map((s) => <Badge key={s} variant="default" radius="sm">{s}</Badge>)}
          </Group>

          <Text size="xs" c="dimmed" mt="lg" mb={6} style={{ letterSpacing: 1 }}>聯繫方式</Text>
          <Stack gap={6}>
            {CONTACTS.map((c) => (
              <Group key={c.label} gap={10} wrap="nowrap" align="flex-start">
                <Text size="xs" c="dimmed" style={{ minWidth: 64, flexShrink: 0 }}>{c.label}</Text>
                <Anchor href={c.href} target="_blank" rel="noopener noreferrer" size="sm"
                  style={{ minWidth: 0, wordBreak: "break-all" }}>
                  {c.href.replace(/^mailto:/, "").replace(/^https?:\/\//, "").replace(/^www\./, "")}
                </Anchor>
              </Group>
            ))}
          </Stack>
        </Paper>
      </Stack>
    </PageContainer>
  );
}
