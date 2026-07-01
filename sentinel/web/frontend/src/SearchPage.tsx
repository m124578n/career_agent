import { Button, Container, Group, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getResume, getSettings, searchJobs, type RecommendedJob } from "./api";
import JobRow from "./JobRow";

export default function SearchPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const [kw, setKw] = useState("");
  const [jobs, setJobs] = useState<RecommendedJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [seeded, setSeeded] = useState(false);
  const canMatch = !!resume.data?.has_resume;

  // 首次載入把關注關鍵字帶入搜尋框（只 seed 一次，不覆寫使用者編輯中）
  useEffect(() => {
    if (!seeded && settings.data) {
      setKw((settings.data.watched_keywords ?? []).join(" "));
      setSeeded(true);
    }
  }, [seeded, settings.data]);

  async function run() {
    if (!kw.trim()) return;
    setErr(null);
    setBusy(true);
    const r = await searchJobs(kw.trim());
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "搜尋失敗");
      return;
    }
    setJobs((await r.json()).jobs);
  }

  return (
    <Container size="md" py="lg">
      <Title order={2} mb="md">職缺搜尋</Title>
      {!canMatch && <Text c="orange" mb="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      <Stack>
        <Group>
          <TextInput
            style={{ flex: 1 }}
            placeholder="輸入關鍵字，如 Python 後端"
            value={kw}
            onChange={(e) => setKw(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === "Enter") run(); }}
          />
          <Button onClick={run} loading={busy} disabled={!kw.trim()}>搜尋</Button>
        </Group>
        {err && <Text c="red" size="sm">{err}</Text>}
        {jobs && jobs.length === 0 && <Text c="dimmed">找不到符合的職缺。</Text>}
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
    </Container>
  );
}
