import { Badge, Button, Group, List, Paper, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconAlertTriangle, IconCheck, IconLock, IconExternalLink } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import {
  diagnoseResume104, getResume, getResume104, openApplyPage,
  type Resume104, type ResumeDiagnosis,
} from "./api";
import BusyHint from "./BusyHint";
import { PageContainer, PageHeader } from "./ui";

export default function Resume104Page() {
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [data, setData] = useState<Resume104 | null>(null);
  const [diag, setDiag] = useState<ResumeDiagnosis | null>(null);
  const [busy, setBusy] = useState(false);
  const [diagBusy, setDiagBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function read() {
    setErr(null); setDiag(null); setBusy(true);
    try {
      const r = await getResume104();
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "讀取失敗"); return; }
      setData(b);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  async function runDiag() {
    if (!data) return;
    setErr(null); setDiagBusy(true);
    try {
      const r = await diagnoseResume104(resume.data?.target_title ?? "", data);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "健檢失敗"); return; }
      setDiag(b);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setDiagBusy(false); }
  }

  async function openEdit() {
    if (!data?.vno) return;
    setErr(null); setApplyBusy(true);
    try {
      const r = await openApplyPage(`https://pda.104.com.tw/profile/edit?vno=${data.vno}`);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "開啟失敗"); }
    } catch { setErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  }

  return (
    <PageContainer>
      <PageHeader
        title="104 履歷"
        subtitle="讀取你 104 上的真實履歷、針對它健檢、開編輯頁親手修改"
        action={<Button onClick={read} loading={busy}>讀取我的 104 履歷</Button>}
      />
      <BusyHint active={busy} label="讀取中" />
      {err && <Text c="danger.6" size="sm" mb="sm">{err}</Text>}
      {data && (
        <Stack gap="md">
          <Group>
            <Badge variant="light" color="teal">完成度 {data.progress}%</Badge>
            <Button size="compact-sm" variant="light" onClick={runDiag} loading={diagBusy}>健檢</Button>
            <BusyHint active={diagBusy} label="分析中" />
            <Button size="compact-sm" leftSection={<IconExternalLink size={15} />}
              onClick={openEdit} loading={applyBusy}>開啟編輯頁</Button>
            <BusyHint active={applyBusy} label="開啟中" />
          </Group>

          {diag && (
            <Group align="flex-start" grow>
              <Paper bg="dark.6" radius="md" p="lg">
                <Group gap={8} mb="sm">
                  <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                  <Text fw={600}>優勢</Text>
                </Group>
                <List size="sm" spacing={6}>{diag.strengths.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
              </Paper>
              <Paper bg="dark.6" radius="md" p="lg">
                <Group gap={8} mb="sm">
                  <ThemeIcon variant="light" color="amber" size="sm"><IconAlertTriangle size={13} /></ThemeIcon>
                  <Text fw={600}>待補強</Text>
                </Group>
                <List size="sm" spacing={6}>{diag.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
              </Paper>
            </Group>
          )}

          {data.blocks.map((b) => (
            <Paper key={b.id} bg="dark.6" radius="md" p="lg">
              <Group gap={8} mb="xs">
                <Text fw={600}>{b.label}</Text>
                {b.is_pii && <Badge size="xs" variant="light" color="gray" leftSection={<IconLock size={10} />}>個資（不送 LLM）</Badge>}
                {b.completed && <Badge size="xs" variant="light" color="teal">已完成</Badge>}
              </Group>
              <Text size="sm" c="dark.1" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{b.text}</Text>
            </Paper>
          ))}
        </Stack>
      )}
    </PageContainer>
  );
}
