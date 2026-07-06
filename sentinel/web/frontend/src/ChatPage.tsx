import {
  ActionIcon, Alert, Badge, Box, Button, Group, List, Loader, Paper, ScrollArea,
  Stack, Text, TextInput, Title, TypographyStylesProvider,
} from "@mantine/core";
import {
  IconBrain, IconCheck, IconCopy, IconDownload, IconEraser, IconExternalLink, IconSearch, IconTrash, IconX,
} from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./chat-md.css";
import {
  applyUpdate, clearChat, deleteMemory, getChat, getResume, getSnapshot, negotiateOffer, openApplyPage,
  readSse, sendChat, SuggestedUpdate, tailorApplication, uploadResume,
  type NegotiationAdvice, type RecommendedJob, type TailoredApplication,
} from "./api";
import { NegotiationView } from "./NegotiateButton";
import JobRow from "./JobRow";

interface UiMsg {
  role: string;
  content: string;
  suggestions?: SuggestedUpdate[];
  remembered?: string[];
  forgot?: string[];
  interrupted?: boolean;
}

const FIELD_LABEL: Record<string, string> = {
  target_title: "目標職稱", expected_salary: "期望薪資", locations: "地點",
  conditions: "軟條件", avoid: "避雷", watched_companies: "關注公司",
  watched_keywords: "關注關鍵字", resume_text: "履歷",
  track: "追蹤", job_offer: "標記錄取", job_reject: "標記未錄取",
  job_reset: "重設狀態", untrack: "取消追蹤", interview_note: "面試紀錄",
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

export default function ChatPage() {
  const qc = useQueryClient();
  const history = useQuery({ queryKey: ["chat"], queryFn: getChat });
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const canMatch = !!resume.data?.has_resume;
  const trackedCodes = new Set(snap.data?.tracked_codes ?? []);
  const [msgs, setMsgs] = useState<UiMsg[]>([]);
  const [search, setSearch] = useState<{ keyword: string; items: RecommendedJob[] } | null>(() => {
    try { const raw = localStorage.getItem("cs_chat_search"); return raw ? JSON.parse(raw) : null; }
    catch { return null; }
  });
  // 最新一次搜尋結果持久化到 localStorage，重整後還原；清空時移除
  useEffect(() => {
    try {
      if (search) localStorage.setItem("cs_chat_search", JSON.stringify(search));
      else localStorage.removeItem("cs_chat_search");
    } catch { /* localStorage 不可用時略過 */ }
  }, [search]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [uploadNote, setUploadNote] = useState<string | null>(null);
  const viewport = useRef<HTMLDivElement>(null);

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
        if (event === "jobs") setSearch({ keyword: data.keyword, items: data.items });
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
      setSearch(null);
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
        <ScrollArea style={{ maxHeight: "calc(100vh - 180px)" }} type="auto">
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
        </ScrollArea>
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
        <Group gap={6} mb="sm">
          <IconSearch size={15} style={{ color: "var(--mantine-color-dark-2)" }} />
          <Text size="sm" fw={600}>搜尋結果{search ? `：${search.keyword}` : ""}</Text>
        </Group>
        {!search && <Text size="xs" c="dimmed">（agent 搜尋後，結果會出現在這）</Text>}
        {search && search.items.length === 0 && <Text size="xs" c="dimmed">找不到符合的職缺</Text>}
        {search && search.items.length > 0 && (
          <ScrollArea style={{ maxHeight: "calc(100vh - 180px)" }} type="auto">
            <Stack gap={6} pr="sm">
              {search.items.map((job) => (
                <JobRow key={job.code} job={job} canMatch={canMatch} tracked={trackedCodes.has(job.code)} />
              ))}
            </Stack>
          </ScrollArea>
        )}
      </Paper>
      </Group>
    </Box>
  );
}
