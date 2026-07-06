import {
  Badge, Button, FileInput, Grid, Group, List, NumberInput, Paper, SegmentedControl,
  Stack, Text, TextInput, Textarea, ThemeIcon,
} from "@mantine/core";
import { IconAlertTriangle, IconCheck, IconLock, IconExternalLink } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  diagnoseResume, getPreferences, getResume, importResume104, openApplyPage, putPreferences,
  uploadResume, type JobPreferences, type Resume104,
} from "./api";
import BusyHint from "./BusyHint";
import { PageContainer, PageHeader } from "./ui";

export default function ProfilePage() {
  const qc = useQueryClient();
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const prefs = useQuery({ queryKey: ["preferences"], queryFn: getPreferences });
  const [source, setSource] = useState("upload");
  const [title, setTitle] = useState("");
  const [salary, setSalary] = useState<number | "">("");
  const [locations, setLocations] = useState("");
  const [conditions, setConditions] = useState("");
  const [avoid, setAvoid] = useState("");
  const [prefBusy, setPrefBusy] = useState(false);
  const [prefErr, setPrefErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [importBusy, setImportBusy] = useState(false);
  const [importErr, setImportErr] = useState<string | null>(null);
  const [r104, setR104] = useState<Resume104 | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);

  useEffect(() => {
    if (prefs.data) {
      setTitle(prefs.data.target_title);
      setSalary(prefs.data.expected_salary ?? "");
      setLocations(prefs.data.locations.join("\n"));
      setConditions(prefs.data.conditions.join("\n"));
      setAvoid(prefs.data.avoid.join("\n"));
    }
  }, [prefs.data]);

  function prefPayload(): JobPreferences {
    const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
    return {
      target_title: title.trim(),
      expected_salary: salary === "" ? null : Number(salary),
      locations: lines(locations), conditions: lines(conditions), avoid: lines(avoid),
    };
  }

  async function savePrefs() {
    setPrefErr(null); setPrefBusy(true);
    try {
      const r = await putPreferences(prefPayload());
      if (!r.ok) { setPrefErr("儲存失敗"); return; }
      qc.invalidateQueries({ queryKey: ["preferences"] });
    } catch { setPrefErr("網路錯誤，請重試"); }
    finally { setPrefBusy(false); }
  }

  const sourceLabel = resume.data?.source === "104" ? "104 匯入"
    : resume.data?.source === "upload" ? "上傳檔案" : "";

  async function onUpload(file: File | null) {
    if (!file) return;
    setErr(null);
    const r = await uploadResume(file);
    if (!r.ok) { setErr("履歷上傳失敗（僅支援 PDF / TXT）"); return; }
    qc.invalidateQueries({ queryKey: ["resume"] });
  }

  async function runImport() {
    setImportErr(null); setImportBusy(true);
    try {
      const r = await importResume104();
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setImportErr(b.detail ?? "匯入失敗"); return; }
      setR104(b.resume104);
      qc.invalidateQueries({ queryKey: ["resume"] });
    } catch { setImportErr("網路錯誤，請重試"); }
    finally { setImportBusy(false); }
  }

  async function openEdit() {
    if (!r104?.vno) return;
    setImportErr(null); setApplyBusy(true);
    try {
      const r = await openApplyPage(`https://pda.104.com.tw/profile/edit?vno=${r104.vno}`);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setImportErr(b.detail ?? "開啟失敗"); }
    } catch { setImportErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  }

  async function runDiagnose() {
    setErr(null); setBusy(true);
    try {
      const pr = await putPreferences(prefPayload());
      if (!pr.ok) { setErr("儲存偏好失敗"); return; }
      qc.invalidateQueries({ queryKey: ["preferences"] });
      const r = await diagnoseResume();
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "健檢失敗"); return; }
      qc.invalidateQueries({ queryKey: ["resume"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  const d = resume.data?.diagnosis;
  return (
    <PageContainer>
      <Stack gap="md">
        <PageHeader title="我的履歷" subtitle="上傳履歷或從 104 匯入，作為比對／客製化／健檢的依據" />

        <Paper bg="dark.6" radius="md" p="lg">
          <Stack>
            <SegmentedControl
              value={source}
              onChange={setSource}
              data={[{ label: "上傳檔案", value: "upload" }, { label: "從 104 匯入", value: "104" }]}
            />

            {source === "upload" && (
              <FileInput label="上傳履歷（PDF / TXT）" placeholder="選擇檔案" accept=".pdf,.txt" onChange={onUpload} />
            )}

            {source === "104" && (
              <Stack gap="sm">
                <Group>
                  <Button onClick={runImport} loading={importBusy}>從 104 匯入</Button>
                  {r104 && (
                    <Button size="compact-sm" variant="light" leftSection={<IconExternalLink size={15} />}
                      onClick={openEdit} loading={applyBusy}>開啟編輯頁</Button>
                  )}
                </Group>
                <BusyHint active={importBusy} label="讀取中" />
                {importErr && <Text c="danger.6" size="sm">{importErr}</Text>}
                {r104 && (
                  <Stack gap="sm">
                    <Badge variant="light" color="teal" w="fit-content">完成度 {r104.progress}%</Badge>
                    {r104.blocks.map((b) => (
                      <Paper key={b.id} bg="dark.7" radius="md" p="md">
                        <Group gap={8} mb="xs">
                          <Text fw={600} size="sm">{b.label}</Text>
                          {b.is_pii && <Badge size="xs" variant="light" color="gray" leftSection={<IconLock size={10} />}>個資（不送 LLM）</Badge>}
                          {b.completed && <Badge size="xs" variant="light" color="teal">已完成</Badge>}
                        </Group>
                        <Text size="sm" c="dark.1" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{b.text}</Text>
                      </Paper>
                    ))}
                  </Stack>
                )}
              </Stack>
            )}

            <Text size="sm" c="dimmed">
              {resume.data?.has_resume
                ? `已載入 ${resume.data.chars} 字${sourceLabel ? `（來源：${sourceLabel}）` : ""}`
                : "尚未設定履歷"}
            </Text>
          </Stack>
        </Paper>

        <Paper bg="dark.6" radius="md" p="lg">
          <Stack>
            <Text fw={600}>求職偏好</Text>
            <Group grow>
              <TextInput label="目標職稱" value={title} onChange={(e) => setTitle(e.currentTarget.value)} />
              <NumberInput label="期望月薪（選填）" value={salary} onChange={(v) => setSalary(typeof v === "number" ? v : "")} />
            </Group>
            <Textarea label="想要的工作地點（一行一個）" autosize minRows={2} value={locations} onChange={(e) => setLocations(e.currentTarget.value)} />
            <Textarea label="軟條件（一行一個，如 可遠端）" autosize minRows={2} value={conditions} onChange={(e) => setConditions(e.currentTarget.value)} />
            <Textarea label="避雷（一行一個，如 博弈）" autosize minRows={2} value={avoid} onChange={(e) => setAvoid(e.currentTarget.value)} />
            {prefErr && <Text c="danger.6" size="sm">{prefErr}</Text>}
            <Group>
              <Button variant="light" onClick={savePrefs} loading={prefBusy}>儲存偏好</Button>
              <Button onClick={runDiagnose} loading={busy} disabled={!resume.data?.has_resume || !title.trim()}>執行健檢</Button>
            </Group>
            {err && <Text c="danger.6" size="sm">{err}</Text>}
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
