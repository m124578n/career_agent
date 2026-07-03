import { Anchor, Button, Group, List, Paper, Progress, Stack, Text } from "@mantine/core";
import { IconStarFilled } from "@tabler/icons-react";
import { useState } from "react";
import { matchJob, type MatchResult, type RecommendedJob } from "./api";
import ResearchButton from "./ResearchButton";

export default function JobRow({ job, canMatch }: { job: RecommendedJob; canMatch: boolean }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);

  async function run() {
    setErr(null);
    setBusy(true);
    const r = await matchJob(job.url);
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "比對失敗");
      return;
    }
    setResult(await r.json());
  }

  return (
    <Paper bg="dark.6" radius="md" px="md" py={12} className="flat-row" style={{ transition: "background-color 200ms" }}>
      <Group justify="space-between" wrap="nowrap">
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            {job.is_watched && (
              <IconStarFilled size={12} style={{ color: "var(--mantine-color-tangerine-5)", flexShrink: 0 }} />
            )}
            <Text fw={600} size="sm" truncate>{job.title}</Text>
            <ResearchButton company={job.company} />
          </Group>
          <Text size="xs" c="dimmed">{job.company} · <Text span c="teal.5" ff="monospace">{job.salary}</Text></Text>
        </div>
        <Group gap="sm" wrap="nowrap">
          <Anchor href={job.url} target="_blank" size="xs" c="dimmed">去 104 看</Anchor>
          <Button size="compact-sm" variant="light" onClick={run} loading={busy} disabled={!canMatch}>比對</Button>
        </Group>
      </Group>
      {err && <Text c="danger.6" size="sm" mt="xs">{err}</Text>}
      {result && (
        <Stack gap={6} mt="sm">
          <Group align="baseline" gap={6}>
            <Text c="teal.5" fw={700} ff="'Space Grotesk', sans-serif" size="xl">{result.score}</Text>
            <Text c="dimmed" size="xs">/ 100</Text>
          </Group>
          <Progress value={result.score} color="teal" size="sm" />
          <Text size="xs" fw={600}>契合理由</Text>
          <List size="xs" spacing={2}>{result.reasons.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
          <Text size="xs" fw={600}>缺少技能 / 待補強</Text>
          <List size="xs" spacing={2}>{result.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
        </Stack>
      )}
    </Paper>
  );
}
