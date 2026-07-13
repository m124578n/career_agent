import { ActionIcon, Badge, Group, Loader, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Feedback } from "../api/client";

export function FeedbackInbox() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["feedback"], queryFn: api.listFeedback });
  const readMut = useMutation({
    mutationFn: ({ id, read }: { id: string; read: boolean }) => api.markFeedbackRead(id, read),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });
  const delMut = useMutation({
    mutationFn: (id: string) => api.deleteFeedback(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feedback"] }),
  });

  const items = data ?? [];
  const unread = items.filter((f) => !f.read).length;

  return (
    <div className="jt-panel" style={{ marginTop: 28 }}>
      <div className="jt-panel-body">
        <Group justify="space-between" mb="md">
          <Text fw={600} fz="sm">意見回饋收件匣</Text>
          {unread > 0 && <Badge color="tangerine">{unread} 未讀</Badge>}
        </Group>
        {isLoading ? (
          <Loader size="sm" />
        ) : items.length === 0 ? (
          <Text fz="sm" c="dimmed">目前沒有回饋。</Text>
        ) : (
          <Stack gap={10}>
            {items.map((f: Feedback) => (
              <div key={f.id} style={{
                borderLeft: `3px solid ${f.read ? "var(--jt-border)" : "var(--jt-tangerine, #e8a05a)"}`,
                paddingLeft: 12,
              }}>
                <Group justify="space-between" wrap="nowrap" gap={8}>
                  <Group gap={8} wrap="nowrap">
                    <Badge size="xs" variant="light">{f.category}</Badge>
                    <Text fz={11} c="dimmed">{f.user}</Text>
                    <Text fz={11} c="dimmed">{new Date(f.created_at).toLocaleString("zh-TW")}</Text>
                  </Group>
                  <Group gap={4} wrap="nowrap" style={{ flexShrink: 0 }}>
                    <ActionIcon size="sm" variant="subtle" color="gray" title={f.read ? "標為未讀" : "標為已讀"}
                      onClick={() => readMut.mutate({ id: f.id, read: !f.read })}>
                      {f.read ? "↺" : "✓"}
                    </ActionIcon>
                    <ActionIcon size="sm" variant="subtle" color="red" title="刪除"
                      onClick={() => delMut.mutate(f.id)}>✕</ActionIcon>
                  </Group>
                </Group>
                <Text fz="sm" mt={4} style={{ whiteSpace: "pre-wrap" }}>{f.message}</Text>
              </div>
            ))}
          </Stack>
        )}
      </div>
    </div>
  );
}
