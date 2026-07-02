import {
  ActionIcon, Alert, Badge, Button, Card, Group, Loader, Paper, ScrollArea,
  Stack, Text, TextInput, Title, TypographyStylesProvider,
} from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./chat-md.css";
import {
  applyUpdate, clearChat, deleteMemory, getChat, readSse, sendChat, SuggestedUpdate,
} from "./api";

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
};

function fmtValue(v: string | number | string[] | null): string {
  if (Array.isArray(v)) return v.join("、");
  return String(v ?? "");
}

function SuggestionCard({ s }: { s: SuggestedUpdate }) {
  const qc = useQueryClient();
  const [state, setState] = useState<"idle" | "busy" | "ok" | "fail">("idle");
  const [msg, setMsg] = useState("");
  const label =
    s.op === "replace_snippet" ? `「${s.old}」→「${s.new}」`
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
    <Card withBorder padding="xs" radius="md">
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
    </Card>
  );
}

export default function ChatPage() {
  const qc = useQueryClient();
  const history = useQuery({ queryKey: ["chat"], queryFn: getChat });
  const [msgs, setMsgs] = useState<UiMsg[]>([]);
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
    <Group align="flex-start" p="md" gap="md" wrap="nowrap">
      <Stack style={{ flex: 1, minWidth: 0 }}>
        <Title order={4}>整理助手</Title>
        <Text size="sm" c="dimmed">
          邊聊邊整理履歷與求職偏好；助手的更新建議需按「套用」才會寫入。
        </Text>
        <ScrollArea h={480} viewportRef={viewport} type="auto">
          <Stack gap="sm" pr="sm">
            {msgs.map((m, i) => (
              <Stack key={i} gap={4} align={m.role === "user" ? "flex-end" : "flex-start"}>
                <Paper
                  withBorder
                  p="sm"
                  radius="md"
                  maw="85%"
                  bg={m.role === "user" ? "dark.5" : undefined}
                >
                  {m.role === "assistant" ? (
                    <TypographyStylesProvider fz="sm" className="chat-md">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                    </TypographyStylesProvider>
                  ) : (
                    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>{m.content}</Text>
                  )}
                  {busy && i === msgs.length - 1 && m.role === "assistant" && (
                    <Loader size="xs" mt={4} />
                  )}
                  {m.interrupted && (
                    <Text size="xs" c="red">回覆中斷</Text>
                  )}
                </Paper>
                {m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}
                {m.remembered?.map((f, j) => (
                  <Badge key={j} variant="light" color="grape">🧠 已記住：{f}</Badge>
                ))}
                {m.forgot?.map((f, j) => (
                  <Badge key={j} variant="light" color="gray">🧹 已忘記：{f}</Badge>
                ))}
              </Stack>
            ))}
            {msgs.length === 0 && (
              <Alert color="gray" variant="light">
                跟我聊聊你的履歷或求職想法，例如「期望薪資改 90 萬」「我只想找雙北的工作」。
              </Alert>
            )}
          </Stack>
        </ScrollArea>
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
      <Card withBorder w={280} style={{ flexShrink: 0 }}>
        <Group justify="space-between" mb="xs">
          <Title order={6}>🧠 半永久記憶</Title>
          <Group gap={4}>
            <Button size="compact-xs" variant="subtle" component="a" href="/api/export">
              匯出 MD
            </Button>
            <Button size="compact-xs" variant="subtle" color="red" onClick={clear}>
              清空對話
            </Button>
          </Group>
        </Group>
        <Stack gap={6}>
          {(history.data?.memory ?? []).map((f, i) => (
            <Group key={i} justify="space-between" wrap="nowrap" gap={4}>
              <Text size="xs" style={{ flex: 1 }}>{f.text}</Text>
              <ActionIcon size="xs" variant="subtle" color="red" onClick={() => removeFact(i)}>
                ✕
              </ActionIcon>
            </Group>
          ))}
          {(history.data?.memory ?? []).length === 0 && (
            <Text size="xs" c="dimmed">（尚無記憶——聊天中提到的長期偏好會自動記在這）</Text>
          )}
        </Stack>
      </Card>
    </Group>
  );
}
