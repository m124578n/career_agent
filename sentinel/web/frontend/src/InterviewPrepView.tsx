import { Anchor, Button, Group, List, Loader, Modal, Stack, Switch, Text } from "@mantine/core";
import { IconNotebook } from "@tabler/icons-react";
import { useState } from "react";
import { interviewPrep, type InterviewPrep } from "./api";

export function InterviewPrepView({ data }: { data: InterviewPrep }) {
  return (
    <Stack gap="sm">
      {data.likely_questions.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>可能考題</Text>
          <List size="sm" spacing={4}>{data.likely_questions.map((q, i) => <List.Item key={i}>{q}</List.Item>)}</List>
        </div>
      )}
      {data.gap_watchouts.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="amber.5" mb={2}>缺口防雷</Text>
          <List size="sm" spacing={4}>{data.gap_watchouts.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
        </div>
      )}
      {data.talking_points.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="teal.5" mb={2}>你的亮點（主動帶出）</Text>
          <List size="sm" spacing={4}>{data.talking_points.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
        </div>
      )}
      {data.prep_checklist.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>準備清單</Text>
          <List size="sm" spacing={4}>{data.prep_checklist.map((p, i) => <List.Item key={i}>{p}</List.Item>)}</List>
        </div>
      )}
      {data.sources.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>參考來源</Text>
          <Stack gap={2}>
            {data.sources.map((s, i) => {
              const safe = /^https?:\/\//i.test(s.url) ? s.url : undefined;
              return safe
                ? <Anchor key={i} href={safe} target="_blank" rel="noopener noreferrer" size="xs">{s.title || s.url}</Anchor>
                : <Text key={i} size="xs" c="dimmed">{s.title || s.url}</Text>;
            })}
          </Stack>
        </div>
      )}
    </Stack>
  );
}

export default function InterviewPrepButton({ code, company, title, initial }: {
  code: string; company?: string; title?: string; initial?: InterviewPrep | null;
}) {
  const label = [company, title].filter(Boolean).join(" · ");
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [deep, setDeep] = useState(false);
  const [data, setData] = useState<InterviewPrep | null>(initial ?? null);

  async function run() {
    setErr(null); setBusy(true);
    try {
      const r = await interviewPrep(code, deep);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "產生失敗"); return; }
      setData(b as InterviewPrep);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  return (
    <>
      <Button size="compact-sm" variant="light" leftSection={<IconNotebook size={14} />}
        onClick={() => setOpened(true)}>面試準備</Button>
      <Modal opened={opened} onClose={() => setOpened(false)} size="lg"
        title={label ? `面試準備：${label}` : "面試準備"}>
        <Group justify="space-between" mb="sm">
          <Switch checked={deep} onChange={(e) => setDeep(e.currentTarget.checked)}
            label="深度模式（上網搜公司面試心得，較慢）" size="sm" />
          <Button size="compact-sm" loading={busy} onClick={run}>
            {data ? "重新產生" : "產生"}
          </Button>
        </Group>
        {busy && (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">{deep ? "搜尋面試心得並整理中（約 20–60 秒）…" : "整理面試準備中…"}</Text>
          </Group>
        )}
        {err && !busy && <Text c="danger.6" size="sm">{err}</Text>}
        {data && !busy && (
          <Stack gap="sm">
            <InterviewPrepView data={data} />
            <Text size="xs" c="dimmed">產於 {data.prepared_at}{data.deep ? "（深度）" : ""}</Text>
          </Stack>
        )}
        {!data && !busy && !err && (
          <Text size="sm" c="dimmed">按「產生」依這個職缺的 JD 與你的履歷做面試準備。</Text>
        )}
      </Modal>
    </>
  );
}
