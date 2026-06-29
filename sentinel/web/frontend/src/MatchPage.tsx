import { Button, Container, List, Progress, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getResume, matchJob, type MatchResult } from "./api";

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
    <Container size="md" py="lg">
      <Title order={2} mb="md">JD 比對</Title>
      {!resume.data?.has_resume && (
        <Text c="orange" mb="sm">請先到「履歷健檢」上傳履歷。</Text>
      )}
      <Stack>
        <TextInput
          label="104 職缺網址"
          placeholder="https://www.104.com.tw/job/xxxxx"
          value={url}
          onChange={(e) => setUrl(e.currentTarget.value)}
        />
        {err && <Text c="red" size="sm">{err}</Text>}
        <Button onClick={run} loading={busy} disabled={!resume.data?.has_resume || !url.trim()}>比對</Button>
        {result && (
          <Stack gap="xs" mt="md">
            <Title order={4}>{result.title}　<Text span c="dimmed" size="sm">{result.company} · {result.salary}</Text></Title>
            <Text>吻合度：{result.score} / 100</Text>
            <Progress value={result.score} />
            <Title order={5} mt="sm">契合理由</Title>
            <List>{result.reasons.map((s, i) => <List.Item key={i}>✓ {s}</List.Item>)}</List>
            <Title order={5} mt="sm">缺少技能 / 待補強</Title>
            <List>{result.gaps.map((g, i) => <List.Item key={i}>! {g}</List.Item>)}</List>
          </Stack>
        )}
      </Stack>
    </Container>
  );
}
