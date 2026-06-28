import { Badge, Button, Card, Container, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getSnapshot, getStatus, startScrape } from "./api";

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card withBorder padding="md" radius="md" style={{ flex: 1, minWidth: 280 }}>
      <Title order={4} mb="sm">{title}（{count}）</Title>
      <Stack gap={8}>{children}</Stack>
    </Card>
  );
}

export default function Dashboard() {
  const qc = useQueryClient();
  const [polling, setPolling] = useState(false);

  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({
    queryKey: ["status"],
    queryFn: getStatus,
    refetchInterval: polling ? 2000 : false,
  });

  useEffect(() => {
    if (polling && status.data && !status.data.running) {
      setPolling(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    }
  }, [polling, status.data?.running, status.data, qc]);

  async function refresh() {
    const r = await startScrape();
    if (r.status === "already_running") { setPolling(true); return; }
    setPolling(true);
  }

  const s = snap.data;
  const running = polling || status.data?.running;

  return (
    <Container size="lg" py="lg">
      <Group justify="space-between" mb="md">
        <Title order={2}>career-sentinel</Title>
        <Group>
          <Text size="sm" c="dimmed">上次更新：{s?.run_at ?? "—"}</Text>
          <Button onClick={refresh} loading={running} disabled={running}>重新抓取</Button>
        </Group>
      </Group>

      {status.data?.last_error && (
        <Text c="red" mb="sm">⚠️ {status.data.last_error}</Text>
      )}
      {s && s.failed_readers.length > 0 && (
        <Text c="orange" mb="sm">⚠️ 本次未讀到：{s.failed_readers.join("、")}（沿用上次）</Text>
      )}

      <Card withBorder padding="md" radius="md" mb="md">
        <Title order={4} mb="xs">今日彙整</Title>
        <Text style={{ whiteSpace: "pre-wrap" }}>{s?.digest ?? "載入中…"}</Text>
      </Card>

      <Group align="flex-start" gap="md" wrap="wrap">
        <Panel title="誰看過我" count={s?.viewers.length ?? 0}>
          {s?.viewers.map((v, i) => (
            <Text key={i} size="sm">{v.company}　<Text span c="dimmed">{v.job_title} · {v.viewed_at}</Text></Text>
          ))}
        </Panel>
        <Panel title="我的應徵" count={s?.applications.length ?? 0}>
          {s?.applications.map((a) => (
            <Text key={a.job_id} size="sm">{a.company} · {a.title}　<Badge size="sm" variant="light">{a.status}</Badge></Text>
          ))}
        </Panel>
        <Panel title="訊息 · 面試" count={s?.messages.length ?? 0}>
          {s?.messages.map((m) => (
            <Text key={m.thread_id} size="sm">
              {m.has_interview_invite && <Badge size="sm" color="orange" mr={6}>面試</Badge>}
              {m.company}：<Text span c="dimmed">{m.last_message}</Text>
            </Text>
          ))}
        </Panel>
      </Group>
    </Container>
  );
}
