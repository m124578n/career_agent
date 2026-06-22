import { Box, Group, Select, Stack, Text, Title } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Application, ApplicationStatus } from "../types";

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

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1400} mx="auto">
      <Stack gap={6} mb={28}>
        <span className="jt-eyebrow">求職 <b>×</b> 追蹤</span>
        <Title order={1} fz={{ base: 28, md: 34 }} fw={700} lts="-0.02em">
          追蹤清單
        </Title>
        <Text c="dimmed" fz="sm">把職缺加入後，在這裡管理投遞與面試進度。</Text>
      </Stack>

      <Group align="flex-start" gap={14} wrap="nowrap" style={{ overflowX: "auto" }}>
        {COLUMNS.map((col) => {
          const items = apps.filter((a) => a.status === col.status);
          return (
            <div key={col.status} className="jt-panel" style={{ minWidth: 260, flex: 1 }}>
              <div className="jt-panel-head">
                <span className="jt-eyebrow">{col.label} · {items.length}</span>
              </div>
              <div className="jt-panel-body">
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
  const statusMut = useMutation({
    mutationFn: (status: ApplicationStatus) =>
      api.updateApplicationStatus(app.job_id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });
  const removeMut = useMutation({
    mutationFn: () => api.removeApplication(app.job_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["applications"] }),
  });

  return (
    <div className="jt-jobcard">
      <Group justify="space-between" wrap="nowrap" mb={6}>
        <a className="jt-job-title" href={app.job.url} target="_blank" rel="noreferrer">
          {app.job.title}
        </a>
        <Text fz="xs" c="dimmed" style={{ cursor: "pointer" }} onClick={() => removeMut.mutate()}>
          ✕
        </Text>
      </Group>
      <div className="jt-job-meta">{app.job.company}</div>
      <Select
        mt={8}
        size="xs"
        value={app.status}
        data={COLUMNS.map((c) => ({ value: c.status, label: c.label }))}
        onChange={(v) => v && statusMut.mutate(v as ApplicationStatus)}
        allowDeselect={false}
      />
    </div>
  );
}
