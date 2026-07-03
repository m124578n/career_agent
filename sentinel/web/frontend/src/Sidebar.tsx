import { Button, NavLink, Stack, Text } from "@mantine/core";
import {
  IconArrowsExchange, IconFileText, IconLayoutDashboard, IconMessageCircle,
  IconRefresh, IconSearch, IconSettings, IconStars, IconWand,
} from "@tabler/icons-react";

export type PageKey = "dashboard" | "resume" | "match" | "recommend" | "search" | "tailor" | "chat";

const NAV: { key: PageKey; label: string; icon: typeof IconSearch }[] = [
  { key: "dashboard", label: "儀表板", icon: IconLayoutDashboard },
  { key: "resume", label: "履歷健檢", icon: IconFileText },
  { key: "match", label: "JD 比對", icon: IconArrowsExchange },
  { key: "recommend", label: "推薦", icon: IconStars },
  { key: "search", label: "職缺搜尋", icon: IconSearch },
  { key: "tailor", label: "客製化", icon: IconWand },
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
