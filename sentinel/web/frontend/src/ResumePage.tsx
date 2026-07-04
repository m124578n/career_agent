import {
  Button, FileInput, Grid, Group, List, NumberInput, Paper, Stack, Text, TextInput, ThemeIcon,
} from "@mantine/core";
import { IconAlertTriangle, IconCheck } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { diagnoseResume, getResume, uploadResume } from "./api";
import BusyHint from "./BusyHint";
import { PageContainer, PageHeader } from "./ui";

export default function ResumePage() {
  const qc = useQueryClient();
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (resume.data) {
      setTitle(resume.data.target_title);
      setSalary(resume.data.expected_salary ?? "");
    }
  }, [resume.data]);

  async function onUpload(file: File | null) {
    if (!file) return;
    setErr(null);
    const r = await uploadResume(file);
    if (!r.ok) { setErr("履歷上傳失敗（僅支援 PDF / TXT）"); return; }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  async function runDiagnose() {
    setErr(null);
    setBusy(true);
    const r = await diagnoseResume(title, salary === "" ? null : Number(salary));
    setBusy(false);
    if (!r.ok) {
      const b = await r.json().catch(() => ({}));
      setErr(b.detail ?? "健檢失敗");
      return;
    }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  const d = resume.data?.diagnosis;
  return (
    <PageContainer>
      <Stack gap="md">
      <PageHeader title="履歷健檢" subtitle="上傳履歷，針對目標職位產出優勢與待補強清單" />
      <Paper bg="dark.6" radius="md" p="lg">
        <Stack>
          <FileInput label="上傳履歷（PDF / TXT）" placeholder="選擇檔案" accept=".pdf,.txt" onChange={onUpload} />
          <Text size="sm" c="dimmed">{resume.data?.has_resume ? `已載入 ${resume.data.chars} 字` : "尚未上傳履歷"}</Text>
          <Group grow>
            <TextInput label="目標職稱" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
            <NumberInput label="期望月薪（選填）" value={salary} onChange={(v) => setSalary(typeof v === "number" ? v : "")} />
          </Group>
          {err && <Text c="danger.6" size="sm">{err}</Text>}
          <Button onClick={runDiagnose} loading={busy} w="fit-content"
            disabled={!resume.data?.has_resume || !title.trim()}>
            執行健檢
          </Button>
          <BusyHint active={busy} label="分析中" />
        </Stack>
      </Paper>
      {d && (
        <Grid mt="md">
          <Grid.Col span={6}>
            <Paper bg="dark.6" radius="md" p="lg" h="100%">
              <Group gap={8} mb="sm">
                <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                <Text fw={600}>優勢</Text>
              </Group>
              <List size="sm" spacing={6}>{d.strengths.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
            </Paper>
          </Grid.Col>
          <Grid.Col span={6}>
            <Paper bg="dark.6" radius="md" p="lg" h="100%">
              <Group gap={8} mb="sm">
                <ThemeIcon variant="light" color="amber" size="sm"><IconAlertTriangle size={13} /></ThemeIcon>
                <Text fw={600}>待補強</Text>
              </Group>
              <List size="sm" spacing={6}>{d.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
            </Paper>
          </Grid.Col>
        </Grid>
      )}
      </Stack>
    </PageContainer>
  );
}
