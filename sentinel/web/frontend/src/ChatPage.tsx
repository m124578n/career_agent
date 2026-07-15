import {
  ActionIcon, Alert, Badge, Box, Button, Collapse, Group, List, Loader, Paper, ScrollArea,
  Stack, Switch, Text, TextInput, Title, TypographyStylesProvider, UnstyledButton,
} from "@mantine/core";
import {
  IconBrain, IconCheck, IconChevronRight, IconCopy, IconDownload, IconEraser, IconExternalLink,
  IconSearch, IconTrash, IconX,
} from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./chat-md.css";
import {
  applyUpdate, clearChat, deleteMemory, getChat, getResearch, getResume, getSnapshot, interviewPrep,
  negotiateOffer, openApplyPage, readSse, searchJobs, sendChat, SuggestedUpdate, tailorApplication, uploadResume,
  type CompanyResearch, type InterviewPrep, type NegotiationAdvice, type RecommendedJob, type TailoredApplication,
} from "./api";
import { InterviewPrepView } from "./InterviewPrepView";
import { NegotiationView } from "./NegotiateButton";
import { ResearchView } from "./ResearchButton";
import JobRow from "./JobRow";

interface UiMsg {
  role: string;
  content: string;
  suggestions?: SuggestedUpdate[];
  remembered?: string[];
  forgot?: string[];
  interrupted?: boolean;
}

interface SearchGroup {
  keyword: string;
  items: RecommendedJob[];
  ts: number;
  page: number;      // 已載入到第幾頁（每頁 20 筆）
  done?: boolean;    // 某頁回傳不足 20 筆 → 已無更多
}

const FIELD_LABEL: Record<string, string> = {
  target_title: "目標職稱", expected_salary: "期望薪資", locations: "地點",
  conditions: "軟條件", avoid: "避雷", watched_companies: "關注公司",
  watched_keywords: "關注關鍵字", resume_text: "履歷",
  track: "追蹤", job_offer: "標記錄取", job_reject: "標記未錄取",
  job_reset: "重設狀態", untrack: "取消追蹤", interview_note: "面試紀錄",
  interview_prep: "面試準備",
};

function fmtValue(v: string | number | string[] | null): string {
  if (Array.isArray(v)) return v.join("、");
  return String(v ?? "");
}

function SuggestionCard({ s }: { s: SuggestedUpdate }) {
  const qc = useQueryClient();
  const [state, setState] = useState<"idle" | "busy" | "ok" | "fail">("idle");
  const [msg, setMsg] = useState("");
  const PIPE_FIELDS = ["track", "job_offer", "job_reject", "job_reset", "untrack", "interview_note"];
  const p = (s.payload ?? {}) as Record<string, any>;
  const pipeLabel =
    s.field === "track" ? `${p.company ?? ""} · ${p.title ?? ""}`
    : s.field === "job_offer"
      ? `${p.company ?? p.code ?? ""}${p.salary_year ? ` · 年薪 ${p.salary_year}` : p.salary_month ? ` · 月薪 ${p.salary_month}` : ""}`
    : s.field === "interview_note"
      ? `${p.when ?? ""}${p.content ? `：${p.content}` : ""}`
    : `${p.company ?? p.code ?? ""}`;
  const label =
    PIPE_FIELDS.includes(s.field) ? pipeLabel
    : s.op === "replace_snippet" ? `「${s.old}」→「${s.new}」`
    : s.op === "append_section" ? `附加：${fmtValue(s.value)}`
    : `→ ${fmtValue(s.value)}`;
  const apply = async () => {
    setState("busy");
    try {
      const r = await applyUpdate(s);
      const body = await r.json().catch(() => ({}));
      if (r.ok && body.ok) {
        setState("ok");
        qc.invalidateQueries({ queryKey: ["resume"] });
        qc.invalidateQueries({ queryKey: ["settings"] });
        if (PIPE_FIELDS.includes(s.field)) qc.invalidateQueries({ queryKey: ["snapshot"] });
      } else {
        setState("fail");
        setMsg(body.message || body.detail || "無法套用");
      }
    } catch {
      setState("fail");
      setMsg("網路錯誤");
    }
  };
  return (
    <Paper bg="dark.6" radius="md" px="md" py="xs">
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm" style={{ wordBreak: "break-all" }}>
          <b>{FIELD_LABEL[s.field] ?? s.field}</b> {label}
        </Text>
        {state === "ok" ? (
          <Badge color="teal">已套用</Badge>
        ) : state === "fail" ? (
          <Badge color="red" title={msg}>無法套用</Badge>
        ) : (
          <Button size="compact-xs" loading={state === "busy"} onClick={apply}>
            套用
          </Button>
        )}
      </Group>
      {state === "fail" && msg && <Text size="xs" c="dimmed">{msg}</Text>}
    </Paper>
  );
}

function TailorCard({ payload }: { payload: { code: string; company?: string; title?: string } }) {
  const url = `https://www.104.com.tw/job/${payload.code}`;
  const [result, setResult] = useState<TailoredApplication | null>(null);
  const [busy, setBusy] = useState(false);
  const [applyBusy, setApplyBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [opened, setOpened] = useState(false);

  const runTailor = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await tailorApplication(url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "生成失敗"); return; }
      setResult(b as TailoredApplication);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };

  const openApply = async () => {
    setErr(null); setApplyBusy(true); setOpened(false);
    try {
      const r = await openApplyPage(url);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "開啟失敗"); return; }
      setOpened(true);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setApplyBusy(false); }
  };

  const copyCover = async () => {
    if (!result) return;
    try {
      await navigator.clipboard.writeText(result.cover_letter);
      setCopied(true); setTimeout(() => setCopied(false), 1500);
    } catch { setErr("複製失敗"); }
  };

  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>客製化</b> {payload.company ?? ""}{payload.title ? ` · ${payload.title}` : ""}</Text>
        {!result && <Button size="compact-xs" loading={busy} onClick={runTailor}>客製化</Button>}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && (
        <Stack gap="sm">
          {result.resume_tips.length > 0 && (
            <div>
              <Text fw={600} size="xs" mb={2}>要強調的重點</Text>
              <List size="xs" spacing={2}>{result.resume_tips.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </div>
          )}
          {result.resume_adjustments.length > 0 && (
            <div>
              <Text fw={600} size="xs" mb={2}>建議調整</Text>
              <List size="xs" spacing={2}>{result.resume_adjustments.map((t, i) => <List.Item key={i}>{t}</List.Item>)}</List>
            </div>
          )}
          {result.missing_keywords.length > 0 && (
            <div>
              <Text fw={600} size="xs" mb={2}>該補的關鍵字</Text>
              <Group gap={6}>{result.missing_keywords.map((k, i) => <Text key={i} size="xs" c="amber.5">{k}</Text>)}</Group>
            </div>
          )}
          <div>
            <Group justify="space-between" mb={2}>
              <Text fw={600} size="xs">求職信</Text>
              <ActionIcon variant="subtle" color="gray" size="sm" onClick={copyCover} title="複製求職信">
                {copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
              </ActionIcon>
            </Group>
            <Text size="xs" style={{ whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{result.cover_letter}</Text>
          </div>
          <Group gap="sm">
            <Button size="compact-sm" leftSection={<IconExternalLink size={14} />} onClick={openApply} loading={applyBusy}>
              開 104 投遞頁
            </Button>
            {opened && <Text size="xs" c="teal.5">已在瀏覽器開啟投遞頁</Text>}
          </Group>
        </Stack>
      )}
    </Paper>
  );
}

function NegotiateCard({ payload }: { payload: { code: string; company?: string; title?: string } }) {
  const [result, setResult] = useState<NegotiationAdvice | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await negotiateOffer(payload.code);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "產生失敗"); return; }
      setResult(b as NegotiationAdvice);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };

  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>談判建議</b> {payload.company ?? ""}{payload.title ? ` · ${payload.title}` : ""}</Text>
        {!result && <Button size="compact-xs" loading={busy} onClick={run}>談判建議</Button>}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && <NegotiationView data={result} />}
    </Paper>
  );
}

function InterviewPrepCard({ payload }: { payload: { code: string; company?: string; title?: string } }) {
  const [result, setResult] = useState<InterviewPrep | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [deep, setDeep] = useState(false);

  const run = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await interviewPrep(payload.code, deep);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "產生失敗"); return; }
      setResult(b as InterviewPrep);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };

  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>面試準備</b> {payload.company ?? ""}{payload.title ? ` · ${payload.title}` : ""}</Text>
        {!result && (
          <Group gap="xs" wrap="nowrap">
            <Switch checked={deep} onChange={(e) => setDeep(e.currentTarget.checked)} size="xs" label="深度" />
            <Button size="compact-xs" loading={busy} onClick={run}>產生</Button>
          </Group>
        )}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && <InterviewPrepView data={result} />}
    </Paper>
  );
}

function ResearchCard({ payload }: { payload: { company?: string } }) {
  const company = payload.company ?? "";
  const [result, setResult] = useState<CompanyResearch | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const run = async () => {
    setErr(null); setBusy(true);
    try {
      const r = await getResearch(company);
      const b = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(b.detail ?? "查詢失敗"); return; }
      setResult(b as CompanyResearch);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  };
  return (
    <Paper bg="dark.6" radius="md" px="md" py="sm" maw="92%">
      <Group justify="space-between" wrap="nowrap" mb={result ? "sm" : 0}>
        <Text size="sm"><b>查公司評價</b> {company}</Text>
        {!result && <Button size="compact-xs" loading={busy} onClick={run}>查評價</Button>}
      </Group>
      {err && <Text size="xs" c="danger.6">{err}</Text>}
      {result && <ResearchView data={result} />}
    </Paper>
  );
}

export default function ChatPage() {
  const qc = useQueryClient();
  const history = useQuery({ queryKey: ["chat"], queryFn: getChat });
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const canMatch = !!resume.data?.has_resume;
  const trackedCodes = new Set(snap.data?.tracked_codes ?? []);
  const [msgs, setMsgs] = useState<UiMsg[]>([]);
  const [searches, setSearches] = useState<SearchGroup[]>(() => {
    try {
      const raw = localStorage.getItem("cs_chat_search");
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      // 舊資料可能沒有 page 欄位，用既有筆數回推目前頁碼
      const withPage = (g: Partial<SearchGroup> & { items?: RecommendedJob[]; keyword?: string }): SearchGroup => ({
        keyword: g.keyword ?? "",
        items: g.items ?? [],
        ts: g.ts ?? Date.now(),
        page: g.page ?? Math.max(1, Math.ceil((g.items?.length ?? 0) / 20)),
        done: g.done,
      });
      if (Array.isArray(parsed)) return parsed.map(withPage);
      // 相容更舊格式（單一搜尋物件）
      if (parsed && Array.isArray(parsed.items)) return [withPage(parsed)];
      return [];
    } catch { return []; }
  });
  // 各次搜尋結果持久化到 localStorage，重整後還原；清空時移除
  useEffect(() => {
    try {
      if (searches.length) localStorage.setItem("cs_chat_search", JSON.stringify(searches));
      else localStorage.removeItem("cs_chat_search");
    } catch { /* localStorage 不可用時略過 */ }
  }, [searches]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const toggleCollapsed = (keyword: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(keyword)) next.delete(keyword); else next.add(keyword);
      return next;
    });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const [moreBusy, setMoreBusy] = useState<Set<string>>(new Set());
  const [moreErr, setMoreErr] = useState<Record<string, string>>({});
  const viewport = useRef<HTMLDivElement>(null);

  // 「載入更多」：前端自己記著關鍵字與頁碼，直接抓下一頁併入該組（不靠 agent 記憶）
  async function loadMore(g: SearchGroup) {
    if (moreBusy.has(g.keyword)) return;
    setMoreBusy((prev) => new Set(prev).add(g.keyword));
    setMoreErr((prev) => { const n = { ...prev }; delete n[g.keyword]; return n; });
    try {
      const r = await searchJobs(g.keyword, g.page + 1);
      if (!r.ok) { setMoreErr((prev) => ({ ...prev, [g.keyword]: "載入更多失敗，請重試" })); return; }
      const data = await r.json();
      const fresh: RecommendedJob[] = data.jobs ?? [];
      setSearches((prev) => prev.map((x) => x.keyword === g.keyword
        ? {
            ...x,
            items: [...x.items, ...fresh.filter((n) => !x.items.some((o) => o.code === n.code))],
            page: g.page + 1,
            done: !data.has_more,
            ts: Date.now(),
          }
        : x));
    } catch {
      setMoreErr((prev) => ({ ...prev, [g.keyword]: "網路錯誤，請重試" }));
    } finally {
      setMoreBusy((prev) => { const s = new Set(prev); s.delete(g.keyword); return s; });
    }
  }

  useEffect(() => {
    if (history.data && !loaded) {
      setMsgs(history.data.messages.map((m) => ({ role: m.role, content: m.content })));
      setLoaded(true);
    }
  }, [history.data, loaded]);

  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight });
  }, [msgs]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    if (text === "/clear") { await clearNow(); return; }  // 固定指令：清空對話（記憶不清）
    setInput("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    const patchLast = (fn: (m: UiMsg) => UiMsg) =>
      setMsgs((m) => [...m.slice(0, -1), fn(m[m.length - 1])]);
    // 平滑打字機：LLM 的 delta 一次來一大塊，先進佇列，再以固定節奏逐字釋放（落後越多吐越快）
    const pending = {
      text: "",
      done: false,
      suggestions: undefined as SuggestedUpdate[] | undefined,
      remembered: undefined as string[] | undefined,
      forgot: undefined as string[] | undefined,
      interrupted: false,
    };
    const drain = window.setInterval(() => {
      if (pending.text) {
        const k = Math.max(1, Math.floor(pending.text.length / 15));
        const chunk = pending.text.slice(0, k);
        pending.text = pending.text.slice(k);
        patchLast((m) => ({ ...m, content: m.content + chunk }));
      } else if (pending.done) {
        window.clearInterval(drain);
        patchLast((m) => ({
          ...m,
          suggestions: pending.suggestions ?? m.suggestions,
          remembered: pending.remembered ?? m.remembered,
          forgot: pending.forgot ?? m.forgot,
          interrupted: pending.interrupted || m.interrupted,
        }));
        setBusy(false);
        qc.invalidateQueries({ queryKey: ["chat"] });
      }
    }, 30);
    try {
      const r = await sendChat(text);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        patchLast((m) => ({ ...m, content: body.detail || "傳送失敗" }));
        pending.interrupted = true;
        return;
      }
      await readSse(r, (event, data) => {
        if (event === "delta") pending.text += data.text;
        if (event === "jobs") setSearches((prev) => {
          // 同關鍵字往下翻頁：併入既有那組（依 code 去重），移到最上；新關鍵字則開新組
          const existing = prev.find((g) => g.keyword === data.keyword);
          const items = existing
            ? [...existing.items, ...data.items.filter(
                (n: RecommendedJob) => !existing.items.some((o) => o.code === n.code))]
            : data.items;
          const evPage = data.page ?? 1;
          return [
            {
              keyword: data.keyword, items, ts: Date.now(),
              page: Math.max(existing?.page ?? 0, evPage),
              done: data.items.length < 20,
            },
            ...prev.filter((g) => g.keyword !== data.keyword),
          ].slice(0, 10);
        });
        if (event === "suggestions") pending.suggestions = data.items;
        if (event === "remembered") pending.remembered = data.facts;
        if (event === "forgot") pending.forgot = data.facts;
        if (event === "error") pending.interrupted = true;
      });
    } catch {
      pending.interrupted = true;
    } finally {
      pending.done = true; // drain 佇列吐完才收尾（解鎖輸入、掛卡片/徽章）
    }
  };

  const clearNow = async () => {
    try {
      await clearChat();
      setMsgs([]);
      setSearches([]);
      setInput("");
      qc.invalidateQueries({ queryKey: ["chat"] });
    } catch {
      window.alert("網路錯誤，請重試");
    }
  };
  const clear = async () => {
    if (!window.confirm("確定清空對話？（半永久記憶不會清除）")) return;
    await clearNow();
  };

  const removeFact = async (i: number) => {
    try {
      await deleteMemory(i);
      qc.invalidateQueries({ queryKey: ["chat"] });
    } catch {
      window.alert("網路錯誤，請重試");
    }
  };

  const handleDropFile = async (file: File) => {
    const name = file.name.toLowerCase();
    if (!name.endsWith(".pdf") && !name.endsWith(".txt")) {
      setUploadNote("只支援 PDF / TXT 履歷檔");
      return;
    }
    setUploadNote("上傳中…");
    try {
      const r = await uploadResume(file);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setUploadNote(body.detail ?? "上傳失敗"); return; }
      setUploadNote(`已設為作用中履歷：${file.name}（${body.chars} 字）`);
      qc.invalidateQueries({ queryKey: ["resume"] });
    } catch { setUploadNote("網路錯誤，請重試"); }
  };

  return (
    <Box mx="auto" px={24} py={32} style={{ maxWidth: 1440 }}>
      <Group align="flex-start" gap="lg" wrap="nowrap">
      <Paper bg="dark.6" radius="md" p="md" w={240} style={{ flexShrink: 0 }}>
        <Group justify="space-between" mb="sm">
          <Group gap={6}>
            <IconBrain size={15} style={{ color: "var(--mantine-color-grape-4)" }} />
            <Text size="sm" fw={600}>半永久記憶</Text>
          </Group>
          <ActionIcon variant="subtle" color="gray" size="sm" component="a" href="/api/export" title="匯出求職檔案 MD">
            <IconDownload size={14} />
          </ActionIcon>
        </Group>
        <ScrollArea.Autosize mah="calc(100vh - 180px)" type="auto">
          <Stack gap={6} pr="sm">
            {(history.data?.memory ?? []).map((f, i) => (
              <Group key={i} justify="space-between" wrap="nowrap" gap={4}>
                <Text size="xs" style={{ flex: 1 }}>{f.text}</Text>
                <ActionIcon size="xs" variant="subtle" color="red" onClick={() => removeFact(i)} title="移除這條記憶">
                  <IconX size={11} />
                </ActionIcon>
              </Group>
            ))}
            {(history.data?.memory ?? []).length === 0 && (
              <Text size="xs" c="dimmed">（尚無記憶——聊天中提到的長期偏好會自動記在這）</Text>
            )}
          </Stack>
        </ScrollArea.Autosize>
      </Paper>
      <Stack style={{ flex: 1, minWidth: 0, height: "calc(100vh - 64px)" }} gap="xs">
        <Group justify="space-between" align="center">
          <Title order={4} style={{ letterSpacing: "-0.3px" }}>求職總指揮</Title>
          <ActionIcon variant="subtle" color="red" size="sm" onClick={clear} title="清空對話（記憶不清；或輸入 /clear）">
            <IconTrash size={15} />
          </ActionIcon>
        </Group>
        <Box
          style={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}
          onDragOver={(e) => { e.preventDefault(); if (!dragActive) setDragActive(true); }}
          onDragLeave={(e) => { e.preventDefault(); setDragActive(false); }}
          onDrop={(e) => {
            e.preventDefault(); setDragActive(false);
            const f = e.dataTransfer.files?.[0];
            if (f) handleDropFile(f);
          }}>
        <ScrollArea style={{ flex: 1, minHeight: 0 }} viewportRef={viewport} type="auto">
          <Stack gap="md" pr="sm" pb={96}>
            {msgs.map((m, i) => (
              <Stack key={i} gap={6} align={m.role === "user" ? "flex-end" : "flex-start"}>
                {m.role === "user" ? (
                  <Paper bg="dark.5" px="md" py="sm" radius="md" maw="85%">
                    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{m.content}</Text>
                  </Paper>
                ) : (
                  <div style={{ maxWidth: "92%" }}>
                    <TypographyStylesProvider fz="sm" className="chat-md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </TypographyStylesProvider>
                    {busy && i === msgs.length - 1 && <Loader size="xs" mt={4} />}
                    {m.interrupted && <Text size="xs" c="danger.6">回覆中斷</Text>}
                  </div>
                )}
                {m.suggestions?.map((s, j) =>
                  s.field === "tailor"
                    ? <TailorCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
                    : s.field === "negotiate"
                      ? <NegotiateCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
                      : s.field === "interview_prep"
                        ? <InterviewPrepCard key={j} payload={(s.payload ?? {}) as { code: string; company?: string; title?: string }} />
                        : s.field === "research"
                          ? <ResearchCard key={j} payload={(s.payload ?? {}) as { company?: string }} />
                          : <SuggestionCard key={j} s={s} />
                )}
                {m.remembered?.map((f, j) => (
                  <Badge key={j} variant="light" color="grape" leftSection={<IconBrain size={12} />}>
                    已記住：{f}
                  </Badge>
                ))}
                {m.forgot?.map((f, j) => (
                  <Badge key={j} variant="light" color="gray" leftSection={<IconEraser size={12} />}>
                    已忘記：{f}
                  </Badge>
                ))}
              </Stack>
            ))}
            {msgs.length === 0 && (
              <div style={{ maxWidth: "92%" }}>
                <TypographyStylesProvider fz="sm" className="chat-md">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{
`嗨，我是你的**求職總指揮** 👋

我可以幫你：
- 整理履歷與求職偏好（目標職稱、薪資、地點）
- 找職缺、讀 JD、比對適合度
- 客製化履歷與求職信、追蹤面試與 offer、給 offer 談判建議

直接跟我說你的狀況或想找什麼吧！（輸入 \`/clear\` 可清空對話，長期記憶不會清）`
                  }</ReactMarkdown>
                </TypographyStylesProvider>
              </div>
            )}
          </Stack>
        </ScrollArea>
        </Box>
        {dragActive && <Text size="xs" c="teal.5">放開以上傳履歷（PDF / TXT）</Text>}
        {uploadNote && (
          <Alert color="gray" variant="light" withCloseButton onClose={() => setUploadNote(null)} py={6}>
            {uploadNote}
          </Alert>
        )}
        <Group wrap="nowrap">
          <TextInput
            style={{ flex: 1 }}
            placeholder="輸入訊息，Enter 送出"
            value={input}
            onChange={(e) => setInput(e.currentTarget.value)}
            onKeyDown={(e) => { if (e.key === "Enter") send(); }}
            disabled={busy}
          />
          <Button onClick={send} loading={busy}>送出</Button>
        </Group>
      </Stack>
      <Paper bg="dark.6" radius="md" p="md" w={440} style={{ flexShrink: 0 }}>
        <Group gap={6} mb="sm" justify="space-between" wrap="nowrap">
          <Group gap={6} wrap="nowrap">
            <IconSearch size={15} style={{ color: "var(--mantine-color-dark-2)" }} />
            <Text size="sm" fw={600}>搜尋結果</Text>
          </Group>
          {searches.length > 0 && (
            <Group gap={6} wrap="nowrap">
              <Badge size="sm" variant="light" color="gray">{searches.length} 次</Badge>
              <ActionIcon size="sm" variant="subtle" color="gray"
                onClick={() => setSearches([])} title="清除全部搜尋">
                <IconTrash size={14} />
              </ActionIcon>
            </Group>
          )}
        </Group>
        {searches.length === 0 && <Text size="xs" c="dimmed">（agent 搜尋後，結果會出現在這）</Text>}
        {searches.length > 0 && (
          <ScrollArea.Autosize mah="calc(100vh - 180px)" type="auto">
            <Stack gap="md" pr="sm">
              {searches.map((g) => {
                const open = !collapsed.has(g.keyword);
                return (
                  <Stack key={g.keyword} gap={6}>
                    <Group gap={6} justify="space-between" wrap="nowrap">
                      <UnstyledButton onClick={() => toggleCollapsed(g.keyword)}
                        style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 4 }}
                        title={open ? "收合" : "展開"}>
                        <IconChevronRight size={13}
                          style={{ flexShrink: 0, color: "var(--mantine-color-dark-2)",
                            transform: open ? "rotate(90deg)" : "none", transition: "transform 150ms" }} />
                        <Text size="xs" fw={600} c="dimmed" truncate>
                          「{g.keyword || "搜尋"}」· {g.items.length} 筆
                        </Text>
                      </UnstyledButton>
                      <ActionIcon size="xs" variant="subtle" color="gray" title="移除這次搜尋"
                        onClick={() => setSearches((prev) => prev.filter((x) => x.keyword !== g.keyword))}>
                        <IconX size={12} />
                      </ActionIcon>
                    </Group>
                    <Collapse in={open}>
                      <Stack gap={6}>
                        {g.items.length === 0
                          ? <Text size="xs" c="dimmed">找不到符合的職缺</Text>
                          : g.items.map((job) => (
                              <JobRow key={job.code} job={job} canMatch={canMatch} tracked={trackedCodes.has(job.code)} compact />
                            ))}
                        {moreErr[g.keyword] && <Text size="xs" c="danger.6">{moreErr[g.keyword]}</Text>}
                        {g.items.length > 0 && (
                          g.done
                            ? <Text size="xs" c="dimmed" ta="center">沒有更多了</Text>
                            : <Button size="compact-sm" variant="subtle" color="gray" fullWidth
                                onClick={() => loadMore(g)} loading={moreBusy.has(g.keyword)}>
                                載入更多 20 筆
                              </Button>
                        )}
                      </Stack>
                    </Collapse>
                  </Stack>
                );
              })}
            </Stack>
          </ScrollArea.Autosize>
        )}
      </Paper>
      </Group>
    </Box>
  );
}
