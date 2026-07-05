import { Button, Group, Modal, NavLink, Stack, Table, Text, UnstyledButton } from "@mantine/core";
import {
  IconCoin, IconFileText, IconLayoutDashboard, IconMessageCircle,
  IconRefresh, IconSearch, IconSettings,
} from "@tabler/icons-react";
import { useDisclosure } from "@mantine/hooks";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getUsage, resetUsage, type UsageSummary } from "./api";

export type PageKey = "dashboard" | "resume" | "jobs" | "chat";

const NAV: { key: PageKey; label: string; icon: typeof IconSearch }[] = [
  { key: "dashboard", label: "儀表板", icon: IconLayoutDashboard },
  { key: "resume", label: "我的履歷", icon: IconFileText },
  { key: "jobs", label: "找職缺", icon: IconSearch },
  { key: "chat", label: "整理助手", icon: IconMessageCircle },
];

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function UsageBadge() {
  const [opened, { open, close }] = useDisclosure(false);
  const qc = useQueryClient();
  const { data } = useQuery<UsageSummary>({
    queryKey: ["usage"],
    queryFn: getUsage,
    refetchInterval: 30000,
  });
  const total = data ?? { total_tokens: 0, total_usd: 0, by_feature: [] };
  return (
    <>
      <UnstyledButton onClick={open} style={{ borderRadius: 8 }}>
        <Group gap={6} justify="center" c="dimmed">
          <IconCoin size={13} stroke={1.7} />
          <Text size="xs" ff="monospace">
            {data ? `${fmtTokens(total.total_tokens)} tok · $${total.total_usd.toFixed(4)}` : "—"}
          </Text>
        </Group>
      </UnstyledButton>
      <Modal opened={opened} onClose={close} title="Token 用量" centered>
        <Text size="sm" mb="sm">
          總計 {total.total_tokens.toLocaleString()} tokens · ${total.total_usd.toFixed(4)}
        </Text>
        <Table striped withTableBorder fz="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>功能</Table.Th><Table.Th>次數</Table.Th>
              <Table.Th>Tokens</Table.Th><Table.Th>USD</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {total.by_feature.map((f) => (
              <Table.Tr key={f.feature}>
                <Table.Td>{f.feature}</Table.Td>
                <Table.Td>{f.calls}</Table.Td>
                <Table.Td>{f.tokens.toLocaleString()}</Table.Td>
                <Table.Td>${f.usd.toFixed(4)}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Button
          mt="md" color="red" variant="light" size="xs" fullWidth
          onClick={async () => {
            await resetUsage();
            qc.invalidateQueries({ queryKey: ["usage"] });
          }}
        >
          歸零
        </Button>
      </Modal>
    </>
  );
}

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
        <UsageBadge />
      </Stack>
    </Stack>
  );
}
