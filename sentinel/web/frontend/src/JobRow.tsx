import { Anchor, Button, Group, List, Paper, Progress, Stack, Text } from "@mantine/core";
import { IconStarFilled } from "@tabler/icons-react";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { matchJob, trackJob, untrackJob, type MatchResult, type RecommendedJob } from "./api";
import BusyHint from "./BusyHint";
import ResearchButton from "./ResearchButton";

export default function JobRow({ job, canMatch, tracked, compact = false }: { job: RecommendedJob; canMatch: boolean; tracked: boolean; compact?: boolean }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);
  const [trackBusy, setTrackBusy] = useState(false);

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

  async function toggleTrack() {
    setErr(null);
    setTrackBusy(true);
    try {
      const r = tracked
        ? await untrackJob(job.code)
        : await trackJob({
            code: job.code, company: job.company, title: job.title,
            url: job.url, salary: job.salary,
            match_score: result ? result.score : null,
          });
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        setErr(b.detail ?? (tracked ? "取消追蹤失敗" : "追蹤失敗"));
        return;
      }
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch {
      setErr("網路錯誤，請重試");
    } finally {
      setTrackBusy(false);
    }
  }

  return (
    <Paper bg="dark.6" radius="md" px="md" py={12} className="flat-row" style={{ transition: "background-color 200ms" }}>
      <Group justify="space-between" wrap="nowrap" align={compact ? "flex-start" : "center"}
        style={compact ? { flexDirection: "column", gap: 10 } : undefined}>
        <div style={{ minWidth: 0, width: compact ? "100%" : undefined }}>
          <Group gap={8} wrap="nowrap">
            {job.is_watched && (
              <IconStarFilled size={12} style={{ color: "var(--mantine-color-tangerine-5)", flexShrink: 0 }} />
            )}
            <Text fw={600} size="sm" truncate>{job.title}</Text>
            <ResearchButton company={job.company} />
          </Group>
          <Text size="xs" c="dimmed">{job.company} · <Text span c="teal.5" ff="monospace">{job.salary}</Text></Text>
        </div>
        <Group gap="sm" wrap="nowrap" justify={compact ? "flex-end" : undefined}
          style={compact ? { width: "100%" } : undefined}>
          <Anchor href={job.url} target="_blank" size="xs" c="dimmed">去 104 看</Anchor>
          <Button size="compact-sm" variant="light" onClick={run} loading={busy} disabled={!canMatch}>比對</Button>
          <Button size="compact-sm" variant={tracked ? "filled" : "outline"} color="teal"
            onClick={toggleTrack} loading={trackBusy}>
            {tracked ? "已追蹤" : "追蹤"}
          </Button>
          <BusyHint active={busy} label="比對中" />
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
