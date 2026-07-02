import {
  ActionIcon, Alert, Badge, Button, Card, Group, Loader, Paper, ScrollArea,
  Stack, Text, TextInput, Title,
} from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import {
  applyUpdate, clearChat, deleteMemory, getChat, readSse, sendChat, SuggestedUpdate,
} from "./api";

interface UiMsg {
  role: string;
  content: string;
  suggestions?: SuggestedUpdate[];
  remembered?: string[];
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
    try {
      const r = await sendChat(text);
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        patchLast((m) => ({ ...m, content: body.detail || "傳送失敗", interrupted: true }));
        return;
      }
      await readSse(r, (event, data) => {
        if (event === "delta") patchLast((m) => ({ ...m, content: m.content + data.text }));
        if (event === "suggestions") patchLast((m) => ({ ...m, suggestions: data.items }));
        if (event === "remembered") {
          patchLast((m) => ({ ...m, remembered: data.facts }));
          qc.invalidateQueries({ queryKey: ["chat"] });
        }
        if (event === "error") patchLast((m) => ({ ...m, interrupted: true }));
      });
    } catch {
      patchLast((m) => ({ ...m, interrupted: true }));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    if (!window.confirm("確定清空對話？（半永久記憶不會清除）")) return;
    await clearChat();
    setMsgs([]);
    qc.invalidateQueries({ queryKey: ["chat"] });
  };

  const removeFact = async (i: number) => {
    await deleteMemory(i);
    qc.invalidateQueries({ queryKey: ["chat"] });
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
                  <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                    {m.content}
                    {busy && i === msgs.length - 1 && m.role === "assistant" && (
                      <Loader size="xs" ml={6} display="inline-block" />
                    )}
                  </Text>
                  {m.interrupted && (
                    <Text size="xs" c="red">回覆中斷</Text>
                  )}
                </Paper>
                {m.suggestions?.map((s, j) => <SuggestionCard key={j} s={s} />)}
                {m.remembered?.map((f, j) => (
                  <Badge key={j} variant="light" color="grape">🧠 已記住：{f}</Badge>
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
          <Button size="compact-xs" variant="subtle" color="red" onClick={clear}>
            清空對話
          </Button>
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
