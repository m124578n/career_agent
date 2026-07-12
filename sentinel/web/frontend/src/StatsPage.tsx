import { Alert, Box, Group, Loader, Paper, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { getStats, type StatsResp } from "./api";

function Bar({ label, value, max, suffix }: { label: string; value: number; max: number; suffix?: string }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <Group gap="sm" wrap="nowrap" align="center">
      <Text size="xs" w={84} style={{ flexShrink: 0 }} ta="right" c="dimmed">{label}</Text>
      <Box style={{ flex: 1, background: "var(--mantine-color-dark-6)", borderRadius: 6, overflow: "hidden" }}>
        <Box style={{ width: `${Math.max(pct, value > 0 ? 6 : 0)}%`, background: "var(--mantine-color-teal-7)",
          height: 22, borderRadius: 6, transition: "width 300ms" }} />
      </Box>
      <Text size="xs" w={64} ff="monospace" style={{ flexShrink: 0 }}>{value}{suffix ?? ""}</Text>
    </Group>
  );
}

function Pct({ title, v }: { title: string; v: number | null }) {
  return (
    <Paper bg="dark.6" radius="md" p="md" style={{ flex: 1 }}>
      <Text size="xs" c="dimmed">{title}</Text>
      <Text fw={700} size="xl" c="teal.4" ff="'Space Grotesk', sans-serif">
        {v === null ? "—" : `${v}%`}
      </Text>
    </Paper>
  );
}

export default function StatsPage() {
  const { data, isLoading, isError } = useQuery<StatsResp>({ queryKey: ["stats"], queryFn: getStats });

  if (isLoading) return <Box p={32}><Loader /></Box>;
  if (isError || !data) return <Box p={32}><Alert color="red">統計載入失敗，請重試。</Alert></Box>;

  const funnelMax = data.funnel.reduce((m, f) => Math.max(m, f.count), 0);
  const dwellMax = data.dwell.reduce((m, d) => Math.max(m, d.median_days ?? 0), 0);
  const hasData = funnelMax > 0 || data.rejected_count > 0;

  return (
    <Box mx="auto" px={24} py={32} style={{ maxWidth: 900 }}>
      <Title order={3} mb="lg" style={{ letterSpacing: "-0.3px" }}>求職統計</Title>

      {!hasData && <Text c="dimmed" size="sm">目前管道還沒有職缺——追蹤幾個職缺後，這裡會出現你的求職漏斗與進度。</Text>}

      {hasData && (
        <Stack gap="xl">
          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} size="sm" mb="md">漏斗（累積達到）</Text>
            <Stack gap={8}>
              {data.funnel.map((f) => <Bar key={f.state} label={f.label} value={f.count} max={funnelMax} />)}
            </Stack>
            {data.rejected_count > 0 && (
              <Text size="xs" c="dimmed" mt="sm">未錄取 {data.rejected_count} 筆（不計入漏斗）</Text>
            )}
          </Paper>

          <div>
            <Text fw={600} size="sm" mb="xs">轉換率</Text>
            <Text size="xs" c="dimmed" mb="sm">仍在進行或已成功的職缺之階段轉換</Text>
            <Group gap="sm">
              <Pct title="投遞 → 面試" v={data.conversions.applied_to_interview} />
              <Pct title="面試 → offer" v={data.conversions.interview_to_offer} />
              <Pct title="有興趣 → offer" v={data.conversions.interested_to_offer} />
            </Group>
          </div>

          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} size="sm" mb="md">各階段中位停留天數</Text>
            <Stack gap={8}>
              {data.dwell.map((d) => (
                d.sample > 0
                  ? <Bar key={d.state} label={d.label} value={d.median_days ?? 0} max={dwellMax} suffix=" 天" />
                  : <Group key={d.state} gap="sm"><Text size="xs" w={84} ta="right" c="dimmed">{d.label}</Text>
                      <Text size="xs" c="dimmed">尚無資料</Text></Group>
              ))}
            </Stack>
          </Paper>

          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} size="sm" mb="md">停滯提醒（超過 14 天未更新）</Text>
            {data.stale.length === 0
              ? <Text size="xs" c="dimmed">沒有停滯的職缺，保持得不錯 👍</Text>
              : <Stack gap={8}>
                  {data.stale.map((j) => (
                    <Group key={j.code} justify="space-between" wrap="nowrap">
                      <Text size="sm" truncate>{j.company || "（公司未知）"} · {j.title || j.code}
                        <Text span c="dimmed" size="xs"> · {j.label}</Text></Text>
                      <Group gap="sm" wrap="nowrap" style={{ flexShrink: 0 }}>
                        <Text size="xs" c="tangerine.5" ff="monospace">{j.days_since_update} 天</Text>
                        {j.url && <Text component="a" href={j.url} target="_blank" size="xs" c="dimmed">去 104 看</Text>}
                      </Group>
                    </Group>
                  ))}
                </Stack>}
          </Paper>
        </Stack>
      )}
    </Box>
  );
}
