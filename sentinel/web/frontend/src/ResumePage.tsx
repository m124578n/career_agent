import { Button, Container, FileInput, List, NumberInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { diagnoseResume, getResume, uploadResume } from "./api";

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
    <Container size="md" py="lg">
      <Title order={2} mb="md">履歷健檢</Title>
      <Stack>
        <FileInput label="上傳履歷（PDF / TXT）" placeholder="選擇檔案" accept=".pdf,.txt" onChange={onUpload} />
        <Text size="sm" c="dimmed">{resume.data?.has_resume ? `已載入 ${resume.data.chars} 字` : "尚未上傳履歷"}</Text>
        <TextInput label="目標職稱" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
        <NumberInput label="期望月薪（選填）" value={salary} onChange={(v) => setSalary(typeof v === "number" ? v : "")} />
        {err && <Text c="red" size="sm">{err}</Text>}
        <Button onClick={runDiagnose} loading={busy} disabled={!resume.data?.has_resume || !title.trim()}>執行健檢</Button>
        {d && (
          <>
            <Title order={4} mt="md">優勢</Title>
            <List>{d.strengths.map((s, i) => <List.Item key={i}>✓ {s}</List.Item>)}</List>
            <Title order={4} mt="md">待補強</Title>
            <List>{d.gaps.map((g, i) => <List.Item key={i}>! {g}</List.Item>)}</List>
          </>
        )}
      </Stack>
    </Container>
  );
}
