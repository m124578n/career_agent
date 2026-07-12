import { Box, Button, Group, Paper, Text, TextInput } from "@mantine/core";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getPreferences, getSalaryInsights, putPreferences, type SalaryInsight } from "./api";

export default function SalaryInsightPanel() {
  const qc = useQueryClient();
  const [kw, setKw] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<SalaryInsight | null>(null);
  const [setting, setSetting] = useState(false);

  async function run() {
    if (!kw.trim()) return;
    setErr(null); setBusy(true); setData(null);
    try {
      const r = await getSalaryInsights(kw.trim());
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "查詢失敗"); return; }
      setData(b as SalaryInsight);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  async function setAsExpected() {
    if (!data?.median_monthly) return;
    setErr(null); setSetting(true);
    try {
      const prefs = await getPreferences();
      const r = await putPreferences({ ...prefs, expected_salary: data.median_monthly });
      if (!r.ok) { setErr("寫入期望薪資失敗，請重試"); return; }
      qc.invalidateQueries({ queryKey: ["preferences"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setSetting(false); }
  }

  return (
    <Paper bg="dark.6" radius="md" p="md">
      <Text fw={600} size="sm" mb="sm">薪資行情（104 搜尋聚合）</Text>
      <Group wrap="nowrap" mb="sm">
        <TextInput style={{ flex: 1 }} placeholder="職稱關鍵字，如 後端工程師" value={kw}
          onChange={(e) => setKw(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === "Enter") run(); }} />
        <Button onClick={run} loading={busy} disabled={!kw.trim()}>查行情</Button>
      </Group>
      {err && <Text c="danger.6" size="sm">{err}</Text>}
      {data && data.sample === 0 && (
        <Text size="sm" c="dimmed">這個關鍵字大多為面議（{data.negotiable} 筆），抓不到可統計的數字。</Text>
      )}
      {data && data.sample > 0 && (
        <Box>
          <Group align="baseline" gap={6}>
            <Text c="teal.4" fw={700} size="xl" ff="'Space Grotesk', sans-serif">
              {data.median_monthly?.toLocaleString()}
            </Text>
            <Text size="xs" c="dimmed">中位月薪</Text>
          </Group>
          <Text size="sm" c="dark.1">
            區間 {data.p25_monthly?.toLocaleString()}–{data.p75_monthly?.toLocaleString()}
            （全距 {data.min_monthly?.toLocaleString()}–{data.max_monthly?.toLocaleString()}）
          </Text>
          <Text size="xs" c="dimmed" mt={4}>
            樣本 {data.sample} 筆 · 面議 {data.negotiable} · 時薪排除 {data.hourly_excluded}
          </Text>
          <Button size="compact-sm" variant="light" mt="sm" loading={setting} onClick={setAsExpected}>
            設為期望月薪
          </Button>
        </Box>
      )}
    </Paper>
  );
}
