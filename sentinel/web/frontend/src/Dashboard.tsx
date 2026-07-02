import { ActionIcon, Anchor, Badge, Box, Group, Text, Title } from "@mantine/core";
import { IconAlertTriangle, IconCalendarPlus, IconStarFilled } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { type Interview, getSnapshot, getStatus } from "./api";
import { Kpi } from "./ui";

function SectionTitle({ children, hint }: { children: React.ReactNode; hint?: string }) {
  return (
    <Title order={5} mt={36} mb="sm" style={{ letterSpacing: "-0.3px" }}>
      {children}
      {hint && <Text span size="xs" c="dimmed" fw={400} ml={8}>{hint}</Text>}
    </Title>
  );
}

function Row({ children }: { children: React.ReactNode }) {
  return (
    <Group justify="space-between" wrap="nowrap" px="md" py={10} mb={6}
      bg="dark.6" style={{ borderRadius: 8, transition: "background-color 200ms" }}>
      {children}
    </Group>
  );
}

const Star = () => (
  <IconStarFilled size={12} style={{ color: "var(--mantine-color-tangerine-5)", flexShrink: 0 }} />
);

export default function Dashboard() {
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({ queryKey: ["status"], queryFn: getStatus });
  const s = snap.data;
  const invites = s?.messages.filter((m) => m.has_interview_invite).length ?? 0;
  const newViewers = status.data?.last_change_counts?.new_viewers ?? 0;

  return (
    <Box p={36} maw={1080}>
      <Group gap={52} align="flex-start">
        <Kpi
          value={s?.viewers.length ?? "—"}
          label="誰看過我"
          suffix={newViewers > 0 ? <Text span c="teal.5" ff="monospace" size="md">+{newViewers}</Text> : undefined}
        />
        <Kpi value={s?.interviews.length ?? "—"} label="即將面試" />
        <Kpi
          value={s?.messages.length ?? "—"}
          label="新訊息"
          suffix={invites > 0 ? <Text span c="amber.5" ff="monospace" size="md">{invites} 邀約</Text> : undefined}
        />
        <Kpi value={s?.applications.length ?? "—"} label="投遞中" />
      </Group>

      {status.data?.last_error && (
        <Group gap={6} mt="lg">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-danger-6)" }} />
          <Text c="danger.6" size="sm">{status.data.last_error}</Text>
        </Group>
      )}
      {s && s.failed_readers.length > 0 && (
        <Group gap={6} mt="sm">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-amber-5)" }} />
          <Text c="amber.5" size="sm">本次未讀到：{s.failed_readers.join("、")}（沿用上次）</Text>
        </Group>
      )}

      {s && s.interviews.length > 0 && (
        <>
          <SectionTitle>即將到來的面試</SectionTitle>
          {s.interviews.map((iv: Interview, i: number) => (
            <Row key={i}>
              <Text size="sm" truncate>
                <Text span fw={600}>{iv.company}</Text>
                <Text span c="dimmed"> · {iv.job_title}{iv.location ? ` · ${iv.location}` : ""}</Text>
              </Text>
              <Group gap="md" wrap="nowrap">
                <Text c="teal.5" ff="monospace" size="xs">{iv.when || "日期未擷取"}</Text>
                {iv.job_url && <Anchor href={iv.job_url} target="_blank" size="xs" c="dimmed">看職缺</Anchor>}
                <ActionIcon component="a" href={iv.gcal_link} target="_blank"
                  variant="default" size="md" title="加入 Google 日曆">
                  <IconCalendarPlus size={15} />
                </ActionIcon>
              </Group>
            </Row>
          ))}
        </>
      )}

      <SectionTitle hint={s?.run_at ? `上次更新 ${s.run_at}` : undefined}>誰看過我</SectionTitle>
      {s?.viewers.map((v, i) => (
        <Row key={i}>
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            {v.watched && <Star />}
            <Text size="sm" truncate>
              <Text span fw={600}>{v.company}</Text>
              <Text span c="dimmed"> · {v.job_title}</Text>
            </Text>
          </Group>
          <Text c="dimmed" ff="monospace" size="xs">{v.viewed_at}</Text>
        </Row>
      ))}

      <SectionTitle>我的應徵</SectionTitle>
      {s?.applications.map((a) => (
        <Row key={a.job_id}>
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            {a.watched && <Star />}
            <Text size="sm" truncate>
              <Text span fw={600}>{a.company}</Text>
              <Text span c="dimmed"> · {a.title}</Text>
            </Text>
          </Group>
          <Badge size="sm" variant="light" color="teal">{a.status}</Badge>
        </Row>
      ))}

      <SectionTitle>訊息 · 面試</SectionTitle>
      {s?.messages.map((m) => (
        <Row key={m.thread_id}>
          <Group gap={8} wrap="nowrap" style={{ minWidth: 0 }}>
            {m.has_interview_invite && <Badge size="xs" variant="light" color="amber">面試</Badge>}
            {m.watched && <Star />}
            <Text size="sm" truncate>
              <Text span fw={600}>{m.company}</Text>
              <Text span c="dimmed">：{m.last_message}</Text>
            </Text>
          </Group>
        </Row>
      ))}

      <SectionTitle>今日彙整</SectionTitle>
      <Text size="sm" c="dark.2" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>
        {s?.digest ?? "載入中…"}
      </Text>
    </Box>
  );
}
