import {
  ActionIcon, Alert, Badge, Button, Divider, Group, Loader, Paper, ScrollArea,
  Stack, Text, TextInput, TypographyStylesProvider,
} from "@mantine/core";
import {
  IconBrain, IconDownload, IconEraser, IconSearch, IconTrash, IconX,
} from "@tabler/icons-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./chat-md.css";
import {
  applyUpdate, clearChat, deleteMemory, getChat, getResume, getSnapshot, readSse, sendChat,
  SuggestedUpdate, type RecommendedJob,
} from "./api";
import JobRow from "./JobRow";
import { PageContainer, PageHeader } from "./ui";

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
  job_reset: "重設狀態", untrack: "取消追蹤",
};

function fmtValue(v: string | number | string[] | null): string {
  if (Array.isArray(v)) return v.join("、");
  return String(v ?? "");
}

function SuggestionCard({ s }: { s: SuggestedUpdate }) {
  const qc = useQueryClient();
  const [state, setState] = useState<"idle" | "busy" | "ok" | "fail">("idle");
  const [msg, setMsg] = useState("");
  const PIPE_FIELDS = ["track", "job_offer", "job_reject", "job_reset", "untrack"];
  const p = (s.payload ?? {}) as Record<string, any>;
  const pipeLabel =
    s.field === "track" ? `${p.company ?? ""} · ${p.title ?? ""}`
    : s.field === "job_offer"
      ? `${p.company ?? p.code ?? ""}${p.salary_year ? ` · 年薪 ${p.salary_year}` : p.salary_month ? ` · 月薪 ${p.salary_month}` : ""}`
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

export default function ChatPage() {
  const qc = useQueryClient();
  const history = useQuery({ queryKey: ["chat"], queryFn: getChat });
  const resume = useQuery({ queryKey: ["resume"], queryFn: getResume });
  const snap = useQuery({ queryKey: ["snapshot"], queryFn: getSnapshot });
  const canMatch = !!resume.data?.has_resume;
  const trackedCodes = new Set(snap.data?.tracked_codes ?? []);
  const [msgs, setMsgs] = useState<UiMsg[]>([]);
  const [search, setSearch] = useState<{ keyword: string; items: RecommendedJob[] } | null>(null);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
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

  const clear = async () => {
    if (!window.confirm("確定清空對話？（半永久記憶不會清除）")) return;
    try {
      await clearChat();
      setMsgs([]);
      setSearch(null);
      qc.invalidateQueries({ queryKey: ["chat"] });
    } catch {
      window.alert("網路錯誤，請重試");
    }
  };

  const removeFact = async (i: number) => {
    try {
      await deleteMemory(i);
      qc.invalidateQueries({ queryKey: ["chat"] });
    } catch {
      window.alert("網路錯誤，請重試");
    }
  };

  return (
    <PageContainer size="lg">
      <Group align="flex-start" gap="xl" wrap="nowrap">
      <Stack style={{ flex: 1, minWidth: 0 }} gap="sm">
        <PageHeader title="求職總指揮" subtitle="邊聊邊整理履歷與偏好、找職缺、追蹤管道；動作需按套用才生效" />
        <Paper withBorder radius="md" bg="dark.7" p="xs" style={{ overflow: "hidden" }}>
        <ScrollArea h="calc(100vh - 360px)" mih={320} viewportRef={viewport} type="auto">
          <Stack gap="md" pr="sm">
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
                {m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}
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
              <Alert color="gray" variant="light">
                跟我聊聊你的履歷或求職想法，例如「期望薪資改 9 萬」「我只想找雙北的工作」。
              </Alert>
            )}
          </Stack>
        </ScrollArea>
        </Paper>
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
      <Paper bg="dark.6" radius="md" p="md" w={360} style={{ flexShrink: 0 }}>
        <Group gap={6} mb="sm">
          <IconSearch size={15} style={{ color: "var(--mantine-color-dark-2)" }} />
          <Text size="sm" fw={600}>搜尋結果{search ? `：${search.keyword}` : ""}</Text>
        </Group>
        {!search && <Text size="xs" c="dimmed" mb="md">（agent 搜尋後，結果會出現在這）</Text>}
        {search && search.items.length === 0 && <Text size="xs" c="dimmed" mb="md">找不到符合的職缺</Text>}
        {search && search.items.length > 0 && (
          <Stack gap={6} mb="md">
            {search.items.map((job) => (
              <JobRow key={job.code} job={job} canMatch={canMatch} tracked={trackedCodes.has(job.code)} />
            ))}
          </Stack>
        )}
        <Divider mb="sm" />
        <Group justify="space-between" mb="sm">
          <Group gap={6}>
            <IconBrain size={15} style={{ color: "var(--mantine-color-grape-4)" }} />
            <Text size="sm" fw={600}>半永久記憶</Text>
          </Group>
          <Group gap={2}>
            <ActionIcon variant="subtle" color="gray" size="sm" component="a" href="/api/export" title="匯出求職檔案 MD">
              <IconDownload size={14} />
            </ActionIcon>
            <ActionIcon variant="subtle" color="red" size="sm" onClick={clear} title="清空對話（記憶不清）">
              <IconTrash size={14} />
            </ActionIcon>
          </Group>
        </Group>
        <Stack gap={6}>
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
      </Paper>
      </Group>
    </PageContainer>
  );
}
