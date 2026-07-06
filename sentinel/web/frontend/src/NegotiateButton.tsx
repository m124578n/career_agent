import { ActionIcon, Anchor, Button, Group, List, Loader, Modal, Stack, Text } from "@mantine/core";
import { IconMoneybag } from "@tabler/icons-react";
import { useState } from "react";
import { negotiateOffer, type NegotiationAdvice } from "./api";

export function NegotiationView({ data }: { data: NegotiationAdvice }) {
  return (
    <Stack gap="sm">
      {data.summary && <Text size="sm" fw={600} style={{ lineHeight: 1.7 }}>{data.summary}</Text>}
      {data.market_assessment && (
        <div>
          <Text size="sm" fw={600} mb={2}>市場評估</Text>
          <Text size="sm" c="dark.1">{data.market_assessment}</Text>
        </div>
      )}
      {data.leverage_points.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="teal.5" mb={2}>你的籌碼</Text>
          <List size="sm" spacing={2}>{data.leverage_points.map((p, i) => <List.Item key={i}>{p}</List.Item>)}</List>
        </div>
      )}
      {data.suggested_ask && (
        <div>
          <Text size="sm" fw={600} mb={2}>建議開價</Text>
          <Text size="sm" c="dark.1">{data.suggested_ask}</Text>
        </div>
      )}
      {data.scripts.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>議價話術</Text>
          <List size="sm" spacing={4}>{data.scripts.map((s, i) => <List.Item key={i}>{s}</List.Item>)}</List>
        </div>
      )}
      {data.risks.length > 0 && (
        <div>
          <Text size="sm" fw={600} c="amber.5" mb={2}>風險</Text>
          <List size="sm" spacing={2}>{data.risks.map((r, i) => <List.Item key={i}>{r}</List.Item>)}</List>
        </div>
      )}
      {data.sources.length > 0 && (
        <div>
          <Text size="sm" fw={600} mb={2}>來源</Text>
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

export default function NegotiateButton({ code, company, title }: { code: string; company?: string; title?: string }) {
  const label = [company, title].filter(Boolean).join(" · ");
  const [opened, setOpened] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [data, setData] = useState<NegotiationAdvice | null>(null);

  async function load() {
    setErr(null); setBusy(true);
    try {
      const r = await negotiateOffer(code);
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setErr(body.detail ?? "產生失敗"); return; }
      setData(body as NegotiationAdvice);
    } catch { setErr("網路錯誤，請重試"); }
    finally { setBusy(false); }
  }

  function open() { setOpened(true); if (!data && !busy) load(); }

  return (
    <>
      <ActionIcon variant="subtle" color="gray" size="xs" title="談判建議"
        style={{ flexShrink: 0 }} onClick={open}>
        <IconMoneybag size={13} />
      </ActionIcon>
      <Modal opened={opened} onClose={() => setOpened(false)} size="lg"
        title={label ? `談判建議：${label}` : "談判建議"}>
        {busy && (
          <Group justify="center" py="xl">
            <Loader size="sm" />
            <Text size="sm" c="dimmed">分析議價策略中（約 20–60 秒）…</Text>
          </Group>
        )}
        {err && !busy && (
          <Stack align="flex-start">
            <Text c="danger.6" size="sm">{err}</Text>
            <Button size="compact-sm" variant="light" onClick={load}>重試</Button>
          </Stack>
        )}
        {data && !busy && (
          <Stack gap="sm">
            <NegotiationView data={data} />
            <Group justify="space-between" mt="xs">
              <Text size="xs" c="dimmed">產於 {data.advised_at}</Text>
              <Button size="compact-xs" variant="subtle" onClick={load}>重新產生</Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}
