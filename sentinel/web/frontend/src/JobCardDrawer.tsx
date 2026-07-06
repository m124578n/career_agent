import {
  ActionIcon, Anchor, Button, Drawer, Group, List, NumberInput, Paper, Progress, Stack,
  Text, Textarea, TextInput, ThemeIcon,
} from "@mantine/core";
import { IconCheck, IconCopy, IconExternalLink } from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  getResume, getTrackedJob, matchJob, openApplyPage, rejectJob, resetTracked, setOffer,
  tailorApplication, trackJob, type MatchResult, type OfferDetail, type TailoredApplication,
} from "./api";
import BusyHint from "./BusyHint";
import ResearchButton from "./ResearchButton";

export interface CardJob {
  code: string;
  company: string;
  title: string;
  url: string;
  salary: string;
}

export default function JobCardDrawer({ job, opened, onClose }: {
  job: CardJob | null;
  opened: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const canMatch = !!resume.data?.has_resume;
  const hasUrl = !!job?.url;

  const [match, setMatch] = useState<MatchResult | null>(null);
  const [tailor, setTailor] = useState<TailoredApplication | null>(null);
  const [matchBusy, setMatchBusy] = useState(false);
  const [tailorBusy, setTailorBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [state, setState] = useState<string>("");
  const [offer, setOfferState] = useState<OfferDetail | null>(null);
  const [editingOffer, setEditingOffer] = useState(false);
  const [form, setForm] = useState<OfferDetail>({
    salary_year: null, salary_month: null, location: "", level: "", start_date: "", notes: "",
  });
  const [stateBusy, setStateBusy] = useState(false);

  // 開啟時載入快取
  useEffect(() => {
    if (!opened || !job) return;
    setErr(null); setMatch(null); setTailor(null);
    setState(""); setOfferState(null); setEditingOffer(false);
    getTrackedJob(job.code).then((r) => r.json()).then((c) => {
      if (c.match) setMatch(c.match);
      if (c.tailor) setTailor(c.tailor);
      setState(c.state || "");
      if (c.offer) {
        setOfferState(c.offer);
        setForm(c.offer);
      } else {
        setForm({ salary_year: null, salary_month: null, location: "", level: "", start_date: "", notes: "" });
      }
    }).catch(() => {});
  }, [opened, job?.code]);

  async function runMatch() {
    if (!job) return;
    setErr(null); setMatchBusy(true);
    try {
      const r = await matchJob(job.url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "比對失敗"); return; }
      setMatch(b);
      const tr = await trackJob({
        code: job.code, company: job.company, title: job.title, url: job.url, salary: job.salary,
        match_score: b.score, match_json: b,
      });
      if (tr.ok) qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setMatchBusy(false); }
  }

  async function runTailor() {
    if (!job) return;
    setErr(null); setTailorBusy(true);
    try {
      const r = await tailorApplication(job.url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "生成失敗"); return; }
      setTailor(b);
      const tr = await trackJob({
        code: job.code, company: job.company, title: job.title, url: job.url, salary: job.salary,
        tailor_json: b,
      });
      if (tr.ok) qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setTailorBusy(false); }
  }

  async function saveOffer() {
    if (!job) return;
    setErr(null); setStateBusy(true);
    try {
      const r = await setOffer(job.code, form);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "儲存失敗"); return; }
      setState("offer"); setOfferState(form); setEditingOffer(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setStateBusy(false); }
  }

  async function markReject() {
    if (!job) return;
    setErr(null); setStateBusy(true);
    try {
      const r = await rejectJob(job.code);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "操作失敗"); return; }
      setState("rejected"); setOfferState(null); setEditingOffer(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setStateBusy(false); }
  }

  async function resetState() {
    if (!job) return;
    setErr(null); setStateBusy(true);
    try {
      const r = await resetTracked(job.code);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "操作失敗"); return; }
      setState("interested"); setOfferState(null); setEditingOffer(false);
      qc.invalidateQueries({ queryKey: ["snapshot"] });
    } catch { setErr("網路錯誤，請重試"); }
    finally { setStateBusy(false); }
  }

  async function copyCover() {
    if (!tailor) return;
    try {
      await navigator.clipboard.writeText(tailor.cover_letter);
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    } catch { setErr("複製失敗"); }
  }

  async function openApply() {
    if (!job) return;
    setErr(null); setApplyBusy(true);
    try {
      const r = await openApplyPage(job.url);
      if (!r.ok) { const b = await r.json().catch(() => ({})); setErr(b.detail ?? "開啟失敗"); }
    } catch { setErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  }

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="lg"
      title={job ? `${job.title} · ${job.company}` : ""}>
      {job && (
        <Stack gap="lg">
          {err && <Text c="danger.6" size="sm">{err}</Text>}

          {/* 狀態 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Text fw={600} mb="sm">狀態</Text>
            {state === "offer" && !editingOffer ? (
              <Stack gap={6}>
                <Text c="teal.5" size="sm" fw={600}>已錄取</Text>
                {offer && (
                  <Text size="xs" c="dimmed">
                    {offer.salary_year != null ? `年薪 ${offer.salary_year}` : ""}
                    {offer.salary_month != null ? ` · 月薪 ${offer.salary_month}` : ""}
                    {offer.location ? ` · ${offer.location}` : ""}
                    {offer.level ? ` · ${offer.level}` : ""}
                    {offer.start_date ? ` · ${offer.start_date}` : ""}
                  </Text>
                )}
                {offer?.notes && <Text size="xs" c="dimmed">{offer.notes}</Text>}
                <Group gap="sm" mt={4}>
                  <Button size="compact-sm" variant="light" onClick={() => setEditingOffer(true)}>編輯</Button>
                  <Button size="compact-sm" variant="subtle" color="gray" onClick={resetState} loading={stateBusy}>重設</Button>
                </Group>
              </Stack>
            ) : state === "rejected" ? (
              <Group justify="space-between">
                <Text c="dimmed" size="sm">已標記未錄取</Text>
                <Button size="compact-sm" variant="subtle" color="gray" onClick={resetState} loading={stateBusy}>重設</Button>
              </Group>
            ) : editingOffer ? (
              <Stack gap="sm">
                <Group grow>
                  <NumberInput label="年薪" value={form.salary_year ?? undefined} thousandSeparator=","
                    onChange={(v) => setForm({ ...form, salary_year: typeof v === "number" ? v : null })} />
                  <NumberInput label="月薪" value={form.salary_month ?? undefined} thousandSeparator=","
                    onChange={(v) => setForm({ ...form, salary_month: typeof v === "number" ? v : null })} />
                </Group>
                <Group grow>
                  <TextInput label="地點" value={form.location}
                    onChange={(e) => setForm({ ...form, location: e.currentTarget.value })} />
                  <TextInput label="職級" value={form.level}
                    onChange={(e) => setForm({ ...form, level: e.currentTarget.value })} />
                </Group>
                <TextInput label="到職日" value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.currentTarget.value })} />
                <Textarea label="備註" autosize minRows={2} value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.currentTarget.value })} />
                <Group gap="sm">
                  <Button size="compact-sm" onClick={saveOffer} loading={stateBusy}>儲存</Button>
                  <Button size="compact-sm" variant="subtle" color="gray" onClick={() => setEditingOffer(false)}>取消</Button>
                </Group>
              </Stack>
            ) : (
              <Group gap="sm">
                <Button size="compact-sm" variant="light" color="teal" onClick={() => setEditingOffer(true)}>標記錄取</Button>
                <Button size="compact-sm" variant="light" color="gray" onClick={markReject} loading={stateBusy}>標記未錄取</Button>
              </Group>
            )}
          </Paper>

          {/* 比對 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>比對</Text>
              {hasUrl && (
                <Button size="compact-sm" variant="light" onClick={runMatch} loading={matchBusy} disabled={!canMatch}>
                  {match ? "重新比對" : "比對"}
                </Button>
              )}
            </Group>
            {!canMatch && <Text c="amber.5" size="xs">請先到「履歷健檢」上傳履歷。</Text>}
            {!hasUrl && <Text c="dimmed" size="xs">此職缺無可用網址，無法比對。</Text>}
            <BusyHint active={matchBusy} label="比對中" />
            {match && (
              <Stack gap={6} mt="sm">
                <Group align="baseline" gap={6}>
                  <Text c="teal.5" fw={700} ff="'Space Grotesk', sans-serif" size="xl">{match.score}</Text>
                  <Text c="dimmed" size="xs">/ 100</Text>
                </Group>
                <Progress value={match.score} color="teal" size="sm" />
                <Text size="xs" fw={600}>契合理由</Text>
                <List size="xs" spacing={2}>{match.reasons.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
                <Text size="xs" fw={600}>缺少技能 / 待補強</Text>
                <List size="xs" spacing={2}>{match.gaps.map((g, i) => <List.Item key={i}>{g}</List.Item>)}</List>
              </Stack>
            )}
          </Paper>

          {/* 研究 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between">
              <Text fw={600}>公司研究</Text>
              <ResearchButton company={job.company} />
            </Group>
          </Paper>

          {/* 客製化 */}
          <Paper bg="dark.6" radius="md" p="lg">
            <Group justify="space-between" mb="sm">
              <Text fw={600}>客製化</Text>
              {hasUrl && (
                <Button size="compact-sm" variant="light" onClick={runTailor} loading={tailorBusy} disabled={!canMatch}>
                  {tailor ? "重新生成" : "客製化"}
                </Button>
              )}
            </Group>
            {!hasUrl && <Text c="dimmed" size="xs">此職缺無可用網址，無法客製化。</Text>}
            <BusyHint active={tailorBusy} label="生成中" />
            {tailor && (
              <Stack gap="md" mt="sm">
                {tailor.resume_tips.length > 0 && (
                  <div>
                    <Group gap={8} mb={4}>
                      <ThemeIcon variant="light" color="teal" size="sm"><IconCheck size={13} /></ThemeIcon>
                      <Text fw={600} size="sm">要強調的重點</Text>
                    </Group>
                    <List size="sm" spacing={4}>{tailor.resume_tips.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
                  </div>
                )}
                {tailor.resume_adjustments.length > 0 && (
                  <div>
                    <Text fw={600} size="sm" mb={4}>建議調整</Text>
                    <List size="sm" spacing={4}>{tailor.resume_adjustments.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
                  </div>
                )}
                {tailor.missing_keywords.length > 0 && (
                  <div>
                    <Text fw={600} size="sm" mb={4}>該補的關鍵字</Text>
                    <Group gap={6}>{tailor.missing_keywords.map((k, i) => <Text key={i} size="sm" c="amber.5">{k}</Text>)}</Group>
                  </div>
                )}
                <div>
                  <Group justify="space-between" mb={4}>
                    <Text fw={600} size="sm">求職信</Text>
                    <ActionIcon variant="subtle" color="gray" onClick={copyCover} title="複製求職信">
                      {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                    </ActionIcon>
                  </Group>
                  <Text size="sm" style={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>{tailor.cover_letter}</Text>
                </div>
                <Button leftSection={<IconExternalLink size={16} />} onClick={openApply} loading={applyBusy} w="fit-content">
                  開啟投遞頁
                </Button>
                <BusyHint active={applyBusy} label="開啟中" />
              </Stack>
            )}
          </Paper>

          <Anchor href={job.url || undefined} target="_blank" size="xs" c="dimmed">
            {job.url ? "去 104 看原始職缺" : ""}
          </Anchor>
        </Stack>
      )}
    </Drawer>
  );
}
