import { Anchor, Badge, Button, Card, Group, List, Progress, Stack, Text } from "@mantine/core";
import { useState } from "react";
import { matchJob, type MatchResult, type RecommendedJob } from "./api";

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
    <Card withBorder padding="md">
      <Group justify="space-between" wrap="nowrap">
        <div>
          <Group gap="xs">
            <Text fw={600}>{job.title}</Text>
            {job.is_watched && <Badge color="orange">★關注</Badge>}
          </Group>
          <Text size="sm" c="dimmed">{job.company} · {job.salary}</Text>
        </div>
        <Group gap="xs" wrap="nowrap">
          <Anchor href={job.url} target="_blank" size="sm">去 104 看</Anchor>
          <Button size="xs" onClick={run} loading={busy} disabled={!canMatch}>比對</Button>
        </Group>
      </Group>
      {err && <Text c="red" size="sm" mt="xs">{err}</Text>}
      {result && (
        <Stack gap="xs" mt="sm">
          <Text size="sm">吻合度：{result.score} / 100</Text>
          <Progress value={result.score} />
          <Text size="sm" fw={600}>契合理由</Text>
          <List size="sm">{result.reasons.map((s, i) => <List.Item key={i}>✓ {s}</List.Item>)}</List>
          <Text size="sm" fw={600}>缺少技能 / 待補強</Text>
          <List size="sm">{result.gaps.map((g, i) => <List.Item key={i}>! {g}</List.Item>)}</List>
        </Stack>
      )}
    </Card>
  );
}
