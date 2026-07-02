import { Button, Stack, Text } from "@mantine/core";
import { IconSparkles } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getRecommend, getResume, type RecommendedJob } from "./api";
import JobRow from "./JobRow";
import { PageHeader } from "./ui";

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
    <Stack p={36} maw={860}>
      <PageHeader
        title="推薦職缺"
        subtitle="拉取 104 個人化推薦，逐筆對履歷比對"
        action={
          <Button leftSection={<IconSparkles size={16} />} onClick={pull} loading={busy}>
            {busy ? "正在開啟瀏覽器拉取…" : "拉取推薦"}
          </Button>
        }
      />
      {!canMatch && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {jobs && jobs.length === 0 && <Text c="dimmed" size="sm">目前沒有推薦職缺。</Text>}
      <Stack gap={6}>
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
    </Stack>
  );
}
