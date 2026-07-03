import {
  ActionIcon, Anchor, Badge, Button, Grid, Group, List, Loader, Modal, Stack, Text,
} from "@mantine/core";
import { IconZoomQuestion } from "@tabler/icons-react";
import { useState } from "react";
import { getResearch, type CompanyResearch } from "./api";

const RISK: Record<string, { color: string; label: string }> = {
  low: { color: "teal", label: "低風險" },
  mid: { color: "amber", label: "中性" },
  high: { color: "danger", label: "高風險" },
};

export default function ResearchButton({ company }: { company: string }) {
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<CompanyResearch | null>(null);

  async function load(force = false) {
    setErr(null);
    setBusy(true);
    try {
      const r = await getResearch(company, force);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(body.detail ?? "查詢失敗"); return; }
      setData(body);
    } catch {
      setErr("網路錯誤，請重試");
    } finally {
      setBusy(false);
    }
  }

  function open() {
    setOpened(true);
    if (!data && !busy) load();
  }

  const risk = RISK[data?.risk_level ?? "mid"] ?? RISK.mid;

  return (
    <>
      <ActionIcon variant="subtle" color="gray" size="xs" title="查公司評價"
        style={{ flexShrink: 0 }} onClick={open}>
        <IconZoomQuestion size={13} />
      </ActionIcon>
      <Modal opened={opened} onClose={() => setOpened(false)} size="lg"
        title={`公司評價：${company}`}>
        {busy && (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">上網研究中（約 20–60 秒）…</Text>
          </Group>
        )}
        {err && !busy && (
          <Stack align="flex-start">
            <Text c="danger.6" size="sm">{err}</Text>
            <Button size="compact-sm" variant="light" onClick={() => load()}>重試</Button>
          </Stack>
        )}
        {data && !busy && (
          <Stack gap="sm">
            <Group gap="xs">
              <Badge color={risk.color} variant="light">{risk.label}</Badge>
              {data.cached && <Text size="xs" c="dimmed">（快取）</Text>}
            </Group>
            <Text size="sm" style={{ lineHeight: 1.7 }}>{data.summary || "（無總評）"}</Text>
            {(data.pros.length > 0 || data.cons.length > 0) && (
              <Grid>
                {data.pros.length > 0 && (
                  <Grid.Col span={6}>
                    <Text size="sm" fw={600} c="teal.5" mb={4}>優點</Text>
                    <List size="sm" spacing={4}>
                      {data.pros.map((p, i) => <List.Item key={i}>{p}</List.Item>)}
                    </List>
                  </Grid.Col>
                )}
                {data.cons.length > 0 && (
                  <Grid.Col span={6}>
                    <Text size="sm" fw={600} c="amber.5" mb={4}>缺點</Text>
                    <List size="sm" spacing={4}>
                      {data.cons.map((c, i) => <List.Item key={i}>{c}</List.Item>)}
                    </List>
                  </Grid.Col>
                )}
              </Grid>
            )}
            {data.salary_notes && (
              <div>
                <Text size="sm" fw={600} mb={2}>薪資觀察</Text>
                <Text size="sm" c="dark.1">{data.salary_notes}</Text>
              </div>
            )}
            {data.interview_notes && (
              <div>
                <Text size="sm" fw={600} mb={2}>面試觀察</Text>
                <Text size="sm" c="dark.1">{data.interview_notes}</Text>
              </div>
            )}
            <div>
              <Text size="sm" fw={600} mb={2}>來源</Text>
              {data.sources.length === 0 && <Text size="sm" c="dimmed">（無來源）</Text>}
              <Stack gap={2}>
                {data.sources.map((s, i) => {
                  const safe = /^https?:\/\//i.test(s.url) ? s.url : undefined;
                  return safe ? (
                    <Anchor key={i} href={safe} target="_blank" rel="noopener noreferrer" size="xs">
                      {s.title || s.url}
                    </Anchor>
                  ) : (
                    <Text key={i} size="xs" c="dimmed">{s.title || s.url}</Text>
                  );
                })}
              </Stack>
            </div>
            <Group justify="space-between" mt="xs">
              <Text size="xs" c="dimmed">查於 {data.researched_at}</Text>
              <Button size="compact-xs" variant="subtle" onClick={() => load(true)}>
                重新查詢
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}
