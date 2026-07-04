import { Button, Group, List, Paper, Progress, Stack, Text, TextInput } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getResume, matchJob, type MatchResult } from "./api";
import BusyHint from "./BusyHint";
import { PageContainer, PageHeader } from "./ui";

export default function MatchPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResult | null>(null);

  async function run() {
    setErr(null);
    setResult(null);
    setBusy(true);
    const r = await matchJob(url.trim());
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "比對失敗");
      return;
    }
    setResult(await r.json());
  }

  return (
    <PageContainer>
      <Stack gap="md">
      <PageHeader title="JD 比對" subtitle="貼上 104 職缺網址，對你的履歷算吻合度與缺口" />
      {!resume.data?.has_resume && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷。</Text>}
      <Group wrap="nowrap">
        <TextInput
          style={{ flex: 1 }}
          placeholder="https://www.104.com.tw/job/xxxxx"
          value={url}
          onChange={(e) => setUrl(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
        />
        <Button onClick={run} loading={busy} disabled={!resume.data?.has_resume || !url.trim()}>比對</Button>
      </Group>
      <BusyHint active={busy} label="比對中" />
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {result && (
        <Paper bg="dark.6" radius="md" p="lg" mt="md">
          <Text fw={600} mb={4}>{result.title}
            <Text span c="dimmed" size="sm"> · {result.company} · {result.salary}</Text>
          </Text>
          <Group align="baseline" gap={8} my="sm">
            <Text c="teal.5" style={{
              fontFamily: "'Space Grotesk', sans-serif", fontSize: 44, fontWeight: 700,
              letterSpacing: "-2px", lineHeight: 1,
            }}>{result.score}</Text>
            <Text c="dimmed" size="sm">/ 100 吻合度</Text>
          </Group>
          <Progress value={result.score} color="teal" mb="md" />
          <Text size="sm" fw={600} mb={4}>契合理由</Text>
          <List size="sm" spacing={4} mb="md">{result.reasons.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
          <Text size="sm" fw={600} mb={4}>缺少技能 / 待補強</Text>
          <List size="sm" spacing={4}>{result.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
        </Paper>
      )}
      </Stack>
    </PageContainer>
  );
}
