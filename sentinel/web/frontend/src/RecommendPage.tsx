import { Button, Container, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getRecommend, getResume, type RecommendedJob } from "./api";
import JobRow from "./JobRow";

export default function RecommendPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [jobs, setJobs] = useState<RecommendedJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const canMatch = !!resume.data?.has_resume;

  async function pull() {
    setErr(null);
    setBusy(true);
    const r = await getRecommend();
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "拉取推薦失敗");
      return;
    }
    setJobs((await r.json()).jobs);
  }

  return (
    <Container size="md" py="lg">
      <Title order={2} mb="md">推薦職缺</Title>
      {!canMatch && <Text c="orange" mb="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      <Stack>
        <Button onClick={pull} loading={busy} w="fit-content">
          {busy ? "正在開啟瀏覽器拉取…" : "拉取推薦"}
        </Button>
        {err && <Text c="red" size="sm">{err}</Text>}
        {jobs && jobs.length === 0 && <Text c="dimmed">目前沒有推薦職缺。</Text>}
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
    </Container>
  );
}
