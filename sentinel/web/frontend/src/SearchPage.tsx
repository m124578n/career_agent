import { Button, Group, Stack, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getResume, getSettings, searchJobs, type RecommendedJob } from "./api";
import BusyHint from "./BusyHint";
import JobRow from "./JobRow";
import { PageContainer, PageHeader } from "./ui";

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
    <PageContainer>
      <Stack gap="md">
      <PageHeader title="職缺搜尋" subtitle="104 站內關鍵字搜尋，逐筆對履歷比對" />
      {!canMatch && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
      <Group wrap="nowrap">
        <TextInput
          style={{ flex: 1 }}
          leftSection={<IconSearch size={15} />}
          placeholder="輸入關鍵字，如 Python 後端"
          value={kw}
          onChange={(e) => setKw(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
        />
        <Button onClick={run} loading={busy} disabled={!kw.trim()}>搜尋</Button>
      </Group>
      <BusyHint active={busy} label="搜尋中" />
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {jobs && jobs.length === 0 && <Text c="dimmed" size="sm">找不到符合的職缺。</Text>}
      <Stack gap={6}>
        {jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} />)}
      </Stack>
      </Stack>
    </PageContainer>
  );
}
