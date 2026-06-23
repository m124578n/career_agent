import {
  Box, Button, Drawer, Group, Modal, Select, Stack, Switch, Table, Text, Textarea,
  TextInput, Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Application, ApplicationStatus, OfferInfo } from "../types";

const COLUMNS: { status: ApplicationStatus; label: string }[] = [
  { status: "to_apply", label: "待投遞" },
  { status: "applied", label: "已投遞" },
  { status: "interviewing", label: "面試中" },
  { status: "offer", label: "Offer" },
  { status: "closed", label: "結束" },
];

export function Applications() {
  const appsQ = useQuery({ queryKey: ["applications"], queryFn: api.listApplications });
  const apps = appsQ.data ?? [];
  const [query, setQuery] = useState("");

  // 關鍵字篩選（職稱／公司），純前端；幾十筆時用來快速定位
  const kw = query.trim().toLowerCase();
  const visible = kw
    ? apps.filter(
        (a) =>
          a.job.title.toLowerCase().includes(kw) ||
          a.job.company.toLowerCase().includes(kw)
      )
    : apps;

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1400} mx="auto">
      <Stack gap={6} mb={20}>
        <span className="jt-eyebrow">求職 <b>×</b> 追蹤</span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          追蹤清單
        </Title>
        <Text c="dimmed" fz="sm">把職缺加入後，在這裡管理投遞與面試進度。</Text>
      </Stack>

      <TextInput
        mb={20}
        size="sm"
        placeholder="搜尋職稱或公司…"
        value={query}
        onChange={(e) => setQuery(e.currentTarget.value)}
        style={{ maxWidth: 360 }}
      />

      <Group align="flex-start" gap={14} wrap="nowrap" style={{ overflowX: "auto" }}>
        {COLUMNS.map((col) => {
          const items = visible.filter((a) => a.status === col.status);
          return (
            <div key={col.status} className="jt-panel" style={{ minWidth: 260, flex: 1 }}>
              <div className="jt-panel-head">
                <span className="jt-eyebrow">{col.label} · {items.length}</span>
                {col.status === "offer" && items.length >= 2 && (
                  <CompareButton offers={items} />
                )}
              </div>
              <div
                className="jt-panel-body"
                style={{ maxHeight: "calc(100vh - 280px)", overflowY: "auto" }}
              >
                <Stack gap={10}>
                  {items.length === 0 ? (
                    <Text fz="xs" c="dimmed">—</Text>
                  ) : (
                    items.map((a) => <AppCard key={a.job_id} app={a} />)
                  )}
                </Stack>
              </div>
            </div>
          );
        })}
      </Group>
    </Box>
  );
}

function AppCard({ app }: { app: Application }) {
  const qc = useQueryClient();
  const [opened, { open, close }] = useDisclosure(false);
  const statusMut = useMutation({
    mutationFn: (status: ApplicationStatus) =>
      api.updateApplicationStatus(app.job_id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
  const removeMut = useMutation({
    mutationFn: () => api.removeApplication(app.job_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  const noteCount = app.events.filter((e) => e.type === "note").length;
  const hasOffer = !!app.offer;

  return (
    <>
      <div className="jt-jobcard" style={{ cursor: "pointer" }} onClick={open}>
        <Group justify="space-between" wrap="nowrap" mb={6}>
          <span className="jt-job-title">{app.job.title}</span>
          <Text fz="xs" c="dimmed" style={{ cursor: "pointer" }}
                onClick={(e) => { e.stopPropagation(); removeMut.mutate(); }}>
            ✕
          </Text>
        </Group>
        <div className="jt-job-meta">{app.job.company}</div>
        <Group gap={8} mt={6}>
          {noteCount > 0 && <Text fz="xs" c="dimmed">💬 {noteCount}</Text>}
          {hasOffer && <Text fz="xs" c="dimmed">💰</Text>}
        </Group>
        <div onClick={(e) => e.stopPropagation()}>
          <Select
            mt={8}
            size="xs"
            value={app.status}
            data={COLUMNS.map((c) => ({ value: c.status, label: c.label }))}
            onChange={(v) => v && statusMut.mutate(v as ApplicationStatus)}
            allowDeselect={false}
          />
        </div>
      </div>
      <AppDrawer app={app} opened={opened} onClose={close} />
    </>
  );
}

function AppDrawer({
  app, opened, onClose,
}: { app: Application; opened: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");
  const [offer, setOffer] = useState<OfferInfo>(app.offer ?? {});

  useEffect(() => {
    if (opened) setOffer(app.offer ?? {});
    // 只在 Drawer 開啟時載入當下的 offer，避免加筆記等 refetch 清掉未存的編輯
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const noteMut = useMutation({
    mutationFn: (note: string) => api.addApplicationNote(app.job_id, note),
    onSuccess: () => {
      setDraft("");
      qc.invalidateQueries({ queryKey: ["applications"] });
    },
  });
  const offerMut = useMutation({
    mutationFn: (o: OfferInfo) => api.setApplicationOffer(app.job_id, o),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  const events = [...app.events].reverse();
  const set = (k: keyof OfferInfo, v: string) =>
    setOffer((o) => ({ ...o, [k]: v }));
  const setAccepted = (v: boolean) => setOffer((o) => ({ ...o, accepted: v }));

  return (
    <Drawer opened={opened} onClose={onClose} position="right" size="md"
            title={<span className="jt-eyebrow">{app.job.company} · {app.job.title}</span>}>
      <Stack gap={16}>
        <a className="jt-job-title" href={app.job.url} target="_blank" rel="noreferrer">
          查看原職缺 ↗
        </a>
        {app.status === "offer" && (
          <div>
            <div className="jt-eyebrow" style={{ marginBottom: 8 }}>OFFER</div>
            <Stack gap={8}>
              <TextInput size="xs" label="薪資" placeholder="月 60k＋年終 2 個月"
                         value={offer.salary ?? ""} onChange={(e) => set("salary", e.currentTarget.value)} />
              <TextInput size="xs" label="職等 / Title" value={offer.level ?? ""}
                         onChange={(e) => set("level", e.currentTarget.value)} />
              <TextInput size="xs" label="到職日" placeholder="2026-08-01"
                         value={offer.start_date ?? ""} onChange={(e) => set("start_date", e.currentTarget.value)} />
              <TextInput size="xs" label="備註" value={offer.note ?? ""}
                         onChange={(e) => set("note", e.currentTarget.value)} />
              <Switch size="sm" label="已接受這個 offer"
                      checked={offer.accepted ?? false}
                      onChange={(e) => setAccepted(e.currentTarget.checked)} />
              <Button size="xs" variant="default" loading={offerMut.isPending}
                      onClick={() => offerMut.mutate(offer)}>儲存 Offer</Button>
            </Stack>
          </div>
        )}

        <div>
          <div className="jt-eyebrow" style={{ marginBottom: 8 }}>時間軸</div>
          <Stack gap={6}>
            {events.length === 0 ? (
              <Text fz="xs" c="dimmed">—</Text>
            ) : (
              events.map((e, i) => (
                <Group key={`${e.ts}-${e.type}-${i}`} gap={8} wrap="nowrap" align="flex-start">
                  <Text fz="xs" c="dimmed" style={{ minWidth: 92 }}>
                    {new Date(e.ts).toLocaleString("zh-TW",
                      { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </Text>
                  <Text fz="xs" c={e.type === "note" ? undefined : "teal"}>
                    {e.type === "note" ? e.note : `狀態 ${e.note}`}
                  </Text>
                </Group>
              ))
            )}
          </Stack>
          <Group gap={8} mt={10} align="flex-end">
            <Textarea size="xs" style={{ flex: 1 }} autosize minRows={1} maxRows={4}
                      placeholder="加一條筆記…" value={draft}
                      onChange={(e) => setDraft(e.currentTarget.value)} />
            <Button size="xs" color="tangerine" loading={noteMut.isPending}
                    disabled={!draft.trim()}
                    onClick={() => noteMut.mutate(draft.trim())}>加入</Button>
          </Group>
        </div>
      </Stack>
    </Drawer>
  );
}

function CompareButton({ offers }: { offers: Application[] }) {
  const [opened, { open, close }] = useDisclosure(false);
  return (
    <>
      <Button size="xs" variant="default" onClick={open}>比較</Button>
      <Modal opened={opened} onClose={close} size="lg"
             title={<span className="jt-eyebrow">OFFER 比較</span>}>
        <Table withTableBorder withColumnBorders fz="xs">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>公司</Table.Th>
              <Table.Th>薪資</Table.Th>
              <Table.Th>職等</Table.Th>
              <Table.Th>到職日</Table.Th>
              <Table.Th>備註</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {offers.map((a) => (
              <Table.Tr key={a.job_id}>
                <Table.Td>{a.job.company}</Table.Td>
                <Table.Td>{a.offer?.salary ?? "—"}</Table.Td>
                <Table.Td>{a.offer?.level ?? "—"}</Table.Td>
                <Table.Td>{a.offer?.start_date ?? "—"}</Table.Td>
                <Table.Td>{a.offer?.note ?? "—"}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Modal>
    </>
  );
}
