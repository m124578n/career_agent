import { Alert, Badge, Button, Card, Container, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { ackSchedule, getSchedule, getSnapshot, getStatus, startScrape } from "./api";
import { ensurePermission, notify } from "./notify";
import SettingsModal from "./SettingsModal";

function Panel({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <Card withBorder padding="md" radius="md" style={{ flex: 1, minWidth: 280 }}>
      <Title order={4} mb="sm">{title}（{count}）</Title>
      <Stack gap={8}>{children}</Stack>
    </Card>
  );
}

export default function Dashboard({ onGoRecommend }: { onGoRecommend: () => void }) {
  const qc = useQueryClient();
  const [polling, setPolling] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const prevDue = useRef(false);

  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const status = useQuery({
    queryKey: ["status"],
    queryFn: getStatus,
    refetchInterval: polling ? 2000 : false,
  });
  const schedule = useQuery({ queryKey: ["schedule"], queryFn: getSchedule, refetchInterval: 30000 });

  useEffect(() => { ensurePermission(); }, []);

  // 到點：due 由 false→true 的邊緣 → 桌面通知（橫幅由 schedule.data.due 直接驅動）
  useEffect(() => {
    const due = schedule.data?.due ?? false;
    if (due && !prevDue.current) {
      notify("⏰ career-sentinel", "該檢視求職動態了，點「立即拉取」更新。");
    }
    prevDue.current = due;
  }, [schedule.data?.due]);

  // scrape 完成：running 由 true→false 的邊緣 → 讀本次新增計數發通知
  useEffect(() => {
    if (polling && status.data && !status.data.running) {
      setPolling(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
      const c = status.data.last_change_counts;
      const total = c ? c.new_viewers + c.status_changes + c.new_messages + c.new_invites : 0;
      if (total > 0) notify("🔔 career-sentinel", `發現 ${total} 筆新動態（看過我／訊息／狀態變化）。`);
    }
  }, [polling, status.data?.running, status.data, qc]);

  async function refresh() {
    const r = await startScrape();
    if (r.status !== "already_running") { /* 開始新的一輪 */ }
    setPolling(true);
  }

  async function onBannerPull() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
    await refresh();
  }

  async function onBannerDismiss() {
    await ackSchedule();
    qc.invalidateQueries({ queryKey: ["schedule"] });
    prevDue.current = false;
  }

  const s = snap.data;
  const running = polling || status.data?.running;
  const due = schedule.data?.due ?? false;

  return (
    <Container size="lg" py="lg">
      <Group justify="space-between" mb="md">
        <Title order={2}>career-sentinel</Title>
        <Group>
          <Text size="sm" c="dimmed">上次更新：{s?.run_at ?? "—"}</Text>
          <Button variant="default" onClick={() => setSettingsOpen(true)}>設定</Button>
          <Button onClick={refresh} loading={running} disabled={running}>重新抓取</Button>
        </Group>
      </Group>

      {due && (
        <Alert color="yellow" mb="md" withCloseButton onClose={onBannerDismiss} title="⏰ 該檢視求職動態了">
          <Group>
            <Button size="xs" onClick={onBannerPull} loading={running} disabled={running}>立即拉取</Button>
            <Button size="xs" variant="light" onClick={onGoRecommend}>也拉推薦</Button>
          </Group>
        </Alert>
      )}

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
      <SettingsModal opened={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </Container>
  );
}
