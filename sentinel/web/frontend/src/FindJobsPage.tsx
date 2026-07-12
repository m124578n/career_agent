import { Button, Group, SegmentedControl, Stack, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  getJobByUrl, getRecommend, getResume, getSettings, getSnapshot,
  searchJobs, type RecommendedJob,
} from "./api";
import BusyHint from "./BusyHint";
import JobRow from "./JobRow";
import SalaryInsightPanel from "./SalaryInsightPanel";
import { PageContainer, PageHeader } from "./ui";

export default function FindJobsPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings });
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const canMatch = !!resume.data?.has_resume;

  const [source, setSource] = useState("search");

  // 關鍵字搜尋
  const [kw, setKw] = useState("");
  const [seeded, setSeeded] = useState(false);
  const [searchJobsList, setSearchJobsList] = useState<RecommendedJob[] | null>(null);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchErr, setSearchErr] = useState<string | null>(null);

  // 推薦
  const [recJobs, setRecJobs] = useState<RecommendedJob[] | null>(null);
  const [recBusy, setRecBusy] = useState(false);
  const [recErr, setRecErr] = useState<string | null>(null);

  // 貼網址
  const [url, setUrl] = useState("");
  const [urlJob, setUrlJob] = useState<RecommendedJob | null>(null);
  const [urlBusy, setUrlBusy] = useState(false);
  const [urlErr, setUrlErr] = useState<string | null>(null);

  useEffect(() => {
    if (!seeded && settings.data) {
      setKw((settings.data.watched_keywords ?? []).join(" "));
      setSeeded(true);
    }
  }, [seeded, settings.data]);

  // 已追蹤的 code 集合（後端 tracked_codes）
  const trackedCodes = new Set(snap.data?.tracked_codes ?? []);

  async function runSearch() {
    if (!kw.trim()) return;
    setSearchErr(null);
    setSearchBusy(true);
    const r = await searchJobs(kw.trim());
    setSearchBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setSearchErr(b.detail ?? "搜尋失敗");
      return;
    }
    setSearchJobsList((await r.json()).jobs);
  }

  async function runRecommend() {
    setRecErr(null);
    setRecBusy(true);
    const r = await getRecommend();
    setRecBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setRecErr(b.detail ?? "拉取推薦失敗");
      return;
    }
    setRecJobs((await r.json()).jobs);
  }

  async function runUrl() {
    if (!url.trim()) return;
    setUrlErr(null);
    setUrlBusy(true);
    const r = await getJobByUrl(url.trim());
    setUrlBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setUrlErr(b.detail ?? "讀取失敗");
      return;
    }
    setUrlJob(await r.json());
  }

  const rows = (jobs: RecommendedJob[] | null) =>
    jobs?.map((j) => <JobRow key={j.code} job={j} canMatch={canMatch} tracked={trackedCodes.has(j.code)} />);

  return (
    <PageContainer>
      <Stack gap="md">
        <PageHeader title="找職缺" subtitle="搜尋、推薦或貼網址找職缺，比對後一鍵追蹤" />
        <SalaryInsightPanel />
        {!canMatch && <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷，才能對職缺做比對。</Text>}
        <SegmentedControl
          value={source}
          onChange={setSource}
          data={[
            { label: "關鍵字搜尋", value: "search" },
            { label: "104 推薦", value: "recommend" },
            { label: "貼網址", value: "url" },
          ]}
        />

        {source === "search" && (
          <>
            <Group wrap="nowrap">
              <TextInput
                style={{ flex: 1 }}
                leftSection={<IconSearch size={15} />}
                placeholder="輸入關鍵字，如 Python 後端"
                value={kw}
                onChange={(e) => setKw(e.currentTarget.value)}
                onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              />
              <Button onClick={runSearch} loading={searchBusy} disabled={!kw.trim()}>搜尋</Button>
            </Group>
            <BusyHint active={searchBusy} label="搜尋中" />
            {searchErr && <Text c="danger.6" size="sm">{searchErr}</Text>}
            {searchJobsList && searchJobsList.length === 0 && <Text c="dimmed" size="sm">找不到符合的職缺。</Text>}
            <Stack gap={6}>{rows(searchJobsList)}</Stack>
          </>
        )}

        {source === "recommend" && (
          <>
            <Button onClick={runRecommend} loading={recBusy} w="fit-content">
              {recBusy ? "正在開啟瀏覽器拉取…" : "拉取 104 推薦"}
            </Button>
            <BusyHint active={recBusy} label="抓取中" />
            {recErr && <Text c="danger.6" size="sm">{recErr}</Text>}
            {recJobs && recJobs.length === 0 && <Text c="dimmed" size="sm">目前沒有推薦職缺。</Text>}
            <Stack gap={6}>{rows(recJobs)}</Stack>
          </>
        )}

        {source === "url" && (
          <>
            <Group wrap="nowrap">
              <TextInput
                style={{ flex: 1 }}
                placeholder="https://www.104.com.tw/job/xxxxx"
                value={url}
                onChange={(e) => setUrl(e.currentTarget.value)}
                onKeyDown={(e) => { if (e.key === "Enter") runUrl(); }}
              />
              <Button onClick={runUrl} loading={urlBusy} disabled={!url.trim()}>讀取</Button>
            </Group>
            <BusyHint active={urlBusy} label="讀取中" />
            {urlErr && <Text c="danger.6" size="sm">{urlErr}</Text>}
            <Stack gap={6}>
              {urlJob && <JobRow key={urlJob.code} job={urlJob} canMatch={canMatch} tracked={trackedCodes.has(urlJob.code)} />}
            </Stack>
          </>
        )}
      </Stack>
    </PageContainer>
  );
}
