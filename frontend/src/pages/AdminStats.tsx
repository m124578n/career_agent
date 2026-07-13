import { Alert, Box, Group, Loader, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { api, type AdminStats as Stats } from "../api/client";

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="jt-panel" style={{ padding: 16 }}>
      <Text fz="xs" c="dimmed">{label}</Text>
      <Text fw={700} fz={26} c="var(--jt-text)" ff="var(--mantine-font-family-monospace)">
        {value.toLocaleString()}
      </Text>
    </div>
  );
}

export function AdminStats() {
  const quota = useQuery({ queryKey: ["quota"], queryFn: api.quota });
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: api.adminStats,
    enabled: !!quota.data?.is_admin,
  });

  if (quota.data && !quota.data.is_admin) {
    return (
      <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
        <Alert color="red">僅管理者可檢視此頁。</Alert>
      </Box>
    );
  }
  if (isLoading || !quota.data) return <Box p={40}><Loader /></Box>;
  if (isError || quota.isError || !data) return <Box p={40}><Alert color="red">數據載入失敗。</Alert></Box>;

  const s: Stats = data;
  const maxUsers = s.daily_active.reduce((m, d) => Math.max(m, d.users), 0);

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
      <span className="jt-eyebrow">營運數據</span>
      <Title order={1} fz={{ base: 26, md: 32 }} fw={700} lts="-0.02em" mb="lg">營運數據</Title>

      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing={12} mb={28}>
        <Tile label="總使用人數" value={s.total_users} />
        <Tile label="近 7 天活躍" value={s.active_7d} />
        <Tile label="近 30 天活躍" value={s.active_30d} />
        <Tile label="總搜尋數" value={s.total_searches} />
        <Tile label="總分析數" value={s.total_analyzed} />
        <Tile label="總投遞數" value={s.total_applications} />
        <Tile label="Tokens" value={s.tokens} />
        <Tile label="LLM 呼叫" value={s.llm_calls} />
      </SimpleGrid>

      <div className="jt-panel">
        <div className="jt-panel-body">
          <Text fw={600} fz="sm" mb="md">近 30 天每日活躍用戶</Text>
          <Stack gap={4}>
            {s.daily_active.map((d) => (
              <Group key={d.day} gap="sm" wrap="nowrap" align="center">
                <Text fz={11} c="dimmed" w={72} ta="right" style={{ flexShrink: 0 }}>
                  {d.day.slice(5)}
                </Text>
                <Box style={{ flex: 1, background: "var(--jt-border)", borderRadius: 4, overflow: "hidden" }}>
                  <Box style={{
                    width: `${maxUsers > 0 ? Math.max((d.users / maxUsers) * 100, d.users > 0 ? 4 : 0) : 0}%`,
                    height: 16, background: "var(--jt-teal)", borderRadius: 4, transition: "width 300ms",
                  }} />
                </Box>
                <Text fz={11} ff="var(--mantine-font-family-monospace)" w={32} style={{ flexShrink: 0 }}>
                  {d.users}
                </Text>
              </Group>
            ))}
          </Stack>
        </div>
      </div>
    </Box>
  );
}
