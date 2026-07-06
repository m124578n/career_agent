import { GoogleLogin } from "@react-oauth/google";
import { notifications } from "@mantine/notifications";
import { Anchor, Box, Group, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";
import { useAuth } from "../state/auth";
import { Footer } from "../components/Footer";
import {
  IconFileText,
  IconTarget,
  IconPenLine,
  IconClipboardCheck,
} from "../components/icons";

const CAPS: { icon: typeof IconFileText; title: string; desc: string }[] = [
  { icon: IconFileText, title: "履歷診斷", desc: "對著目標職位，找出你的亮點與可加強的地方。" },
  { icon: IconTarget, title: "職缺契合度", desc: "搜尋 104 職缺，逐筆比對你的履歷並排序。" },
  { icon: IconPenLine, title: "求職信生成", desc: "依職缺與你的背景，一鍵生成可編輯的求職信。" },
  { icon: IconClipboardCheck, title: "投遞追蹤", desc: "用看板管理投遞與面試進度，offer 一目了然。" },
];

export function Landing() {
  const { login } = useAuth();
  return (
    <Box style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <Group justify="space-between" px={{ base: "lg", md: 40 }} py="md">
        <span className="jt-brand">
          JobTracker<span className="dot" aria-hidden="true">.</span>
        </span>
        <Group gap="lg">
          <Anchor component={Link} to="/self-host" c="dimmed" fz="sm">
            本機自架版 →
          </Anchor>
          <Anchor component={Link} to="/about" c="dimmed" fz="sm">
            關於作者 →
          </Anchor>
        </Group>
      </Group>

      <Box p={{ base: "lg", md: 40 }} maw={960} mx="auto" w="100%" style={{ flex: 1 }}>
        <Stack align="center" gap={10} mt={{ base: 24, md: 56 }} mb={44} ta="center">
          <span className="jt-eyebrow">AI 求職指揮艙</span>
          <Title order={1} fz={{ base: 34, md: 52 }} fw={700} lts="-0.03em" maw={680}>
            從履歷到 offer，一站幫你搞定
          </Title>
          <Text c="dimmed" fz={{ base: "sm", md: "md" }} maw={520}>
            上傳履歷、設定目標，AI 幫你看亮點、找契合職缺、寫求職信、追蹤投遞進度。
          </Text>
          <Stack align="center" gap={10} mt={18}>
            <GoogleLogin
              onSuccess={(r) => r.credential && login(r.credential)}
              onError={() =>
                notifications.show({
                  color: "red",
                  title: "登入失敗",
                  message: "Google 登入沒有完成，請再試一次。",
                })
              }
              theme="filled_black"
              shape="pill"
            />
            <Text fz="xs" c="dimmed">
              由{" "}
              <Anchor component={Link} to="/about" c="dimmed" style={{ textDecoration: "underline" }}>
                詹舜智
              </Anchor>{" "}
              打造 · 每日免費額度
            </Text>
          </Stack>
        </Stack>

        <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }} spacing={16}>
          {CAPS.map((c) => (
            <div key={c.title} className="jt-panel" style={{ padding: 20 }}>
              <div style={{ color: "var(--jt-teal)", marginBottom: 12 }}>
                <c.icon size={24} />
              </div>
              <Text fw={600} fz="sm" mb={6} c="var(--jt-text)">
                {c.title}
              </Text>
              <Text fz="xs" c="dimmed" style={{ lineHeight: 1.6 }}>
                {c.desc}
              </Text>
            </div>
          ))}
        </SimpleGrid>
      </Box>
      <Footer />
    </Box>
  );
}
