import {
  ActionIcon, Button, Group, List, Paper, Stack, Text, TextInput, ThemeIcon,
} from "@mantine/core";
import { IconCheck, IconCopy, IconAlertTriangle } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getResume, tailorApplication, type TailoredApplication } from "./api";
import { PageContainer, PageHeader } from "./ui";

export default function TailorPage() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<TailoredApplication | null>(null);
  const [copied, setCopied] = useState(false);

  async function run() {
    if (!url.trim()) return;
    setErr(null);
    setData(null);
    setBusy(true);
    try {
      const r = await tailorApplication(url.trim());
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(body.detail ?? "生成失敗"); return; }
      setData(body);
    } catch {
      setErr("網路錯誤，請重試");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    if (!data) return;
    try {
      await navigator.clipboard.writeText(data.cover_letter);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setErr("複製失敗");
    }
  }

  return (
    <PageContainer>
      <PageHeader title="客製化" subtitle="貼 104 職缺網址，針對該職缺產履歷客製化建議與求職信" />
      {!resume.data?.has_resume && (
        <Group gap={6} mb="sm">
          <IconAlertTriangle size={15} style={{ color: "var(--mantine-color-amber-5)" }} />
          <Text c="amber.5" size="sm">請先到「履歷健檢」上傳履歷。</Text>
        </Group>
      )}
      <Group wrap="nowrap">
        <TextInput
          style={{ flex: 1 }}
          placeholder="https://www.104.com.tw/job/xxxxx"
          value={url}
          onChange={(e) => setUrl(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }}
        />
        <Button onClick={run} loading={busy} disabled={!resume.data?.has_resume || !url.trim()}>
          客製化
        </Button>
      </Group>
      {err && <Text c="danger.6" size="sm" mt="sm">{err}</Text>}
      {data && (
        <Stack gap="md" mt="lg">
          <Text fw={600}>{data.job_title}
            <Text span c="dimmed" size="sm"> · {data.company}</Text>
          </Text>
          {data.resume_tips.length > 0 && (
            <Paper bg="dark.6" radius="md" p="lg">
              <Group gap={8} mb="sm">
                <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                <Text fw={600}>要強調的重點</Text>
              </Group>
              <List size="sm" spacing={6}>{data.resume_tips.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </Paper>
          )}
          {data.resume_adjustments.length > 0 && (
            <Paper bg="dark.6" radius="md" p="lg">
              <Text fw={600} mb="sm">建議調整</Text>
              <List size="sm" spacing={6}>{data.resume_adjustments.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </Paper>
          )}
          {data.missing_keywords.length > 0 && (
            <Paper bg="dark.6" radius="md" p="lg">
              <Text fw={600} mb="sm">該補的關鍵字</Text>
              <Group gap={6}>
                {data.missing_keywords.map((k, i) => (
                  <Text key={i} size="sm" c="amber.5">{k}</Text>
                ))}
              </Group>
            </Paper>
          )}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>求職信</Text>
              <ActionIcon variant="subtle" color="gray" onClick={copy} title="複製求職信">
                {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              </ActionIcon>
            </Group>
            <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>{data.cover_letter}</Text>
          </Paper>
        </Stack>
      )}
    </PageContainer>
  );
}
