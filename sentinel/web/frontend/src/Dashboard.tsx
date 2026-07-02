import { Anchor, Badge, Button, Card, Container, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { type Interview, getSnapshot, getStatus } from "./api";

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card withBorder padding="md" radius="md" style={{ flex: 1, minWidth: 280 }}>
      <Title order={4} mb="sm">{title}（{count}）</Title>
      <Stack gap={8}>{children}</Stack>
    </Card>
  );
}

export default function Dashboard() {
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({ queryKey: ["status"], queryFn: getStatus });
  const s = snap.data;

  return (
    <Container size="lg" py="lg">
      <Group justify="space-between" mb="md">
        <Title order={2}>儀表板</Title>
        <Text size="sm" c="dimmed">上次更新：{s?.run_at ?? "—"}</Text>
      </Group>

      {status.data?.last_error && (
        <Text c="red" mb="sm">{status.data.last_error}</Text>
      )}
      {s && s.failed_readers.length > 0 && (
        <Text c="orange" mb="sm">本次未讀到：{s.failed_readers.join("、")}（沿用上次）</Text>
      )}

      {s && s.interviews.length > 0 && (
        <Card withBorder padding="md" radius="md" mb="md">
          <Title order={4} mb="sm">即將到來的面試（{s.interviews.length}）</Title>
          <Stack gap="xs">
            {s.interviews.map((iv: Interview, i: number) => (
              <Group key={i} justify="space-between" wrap="nowrap">
                <div>
                  <Text fw={600}>{iv.company}　<Text span c="dimmed" size="sm">{iv.job_title}</Text></Text>
                  <Text size="sm" c="dimmed">
                    {iv.when || "日期未擷取"}{iv.location ? ` · ${iv.location}` : ""}
                  </Text>
                </div>
                <Group gap="xs" wrap="nowrap">
                  {iv.job_url && <Anchor href={iv.job_url} target="_blank" size="sm">看職缺</Anchor>}
                  <Button component="a" href={iv.gcal_link} target="_blank" size="xs" variant="light">加入 Google 日曆</Button>
                </Group>
              </Group>
            ))}
          </Stack>
        </Card>
      )}

      <Card withBorder padding="md" radius="md" mb="md">
        <Title order={4} mb="xs">今日彙整</Title>
        <Text style={{ whiteSpace: "pre-wrap" }}>{s?.digest ?? "載入中…"}</Text>
      </Card>

      <Group align="flex-start" gap="md" wrap="wrap">
        <Panel title="誰看過我" count={s?.viewers.length ?? 0}>
          {s?.viewers.map((v, i) => (
            <Text key={i} size="sm">{v.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}{v.company}　<Text span c="dimmed">{v.job_title} · {v.viewed_at}</Text></Text>
          ))}
        </Panel>
        <Panel title="我的應徵" count={s?.applications.length ?? 0}>
          {s?.applications.map((a) => (
            <Text key={a.job_id} size="sm">{a.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}{a.company} · {a.title}　<Badge size="sm" variant="light">{a.status}</Badge></Text>
          ))}
        </Panel>
        <Panel title="訊息 · 面試" count={s?.messages.length ?? 0}>
          {s?.messages.map((m) => (
            <Text key={m.thread_id} size="sm">
              {m.has_interview_invite && <Badge size="sm" color="orange" mr={6}>面試</Badge>}
              {m.watched && <Badge size="sm" color="yellow" mr={6}>★關注</Badge>}
              {m.company}：<Text span c="dimmed">{m.last_message}</Text>
            </Text>
          ))}
        </Panel>
      </Group>
    </Container>
  );
}
