import { Button, Group, Modal, Select, Stack, Text, Textarea, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { api } from "../api/client";

const CATEGORIES = ["建議", "問題回報", "其他"];

export function FeedbackButton() {
  const [opened, { open, close }] = useDisclosure(false);
  const [message, setMessage] = useState("");
  const [category, setCategory] = useState<string>("建議");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    if (!message.trim()) return;
    setErr(null); setBusy(true);
    try {
      await api.submitFeedback(message.trim(), category);
      setMessage("");
      close();
      notifications.show({ color: "teal", title: "已送出", message: "感謝你的回饋！" });
    } catch {
      setErr("送出失敗，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <UnstyledButton onClick={open} style={{ padding: "6px 8px", borderRadius: 8 }}>
        <Text fz={12} c="dimmed">💬 意見回饋</Text>
      </UnstyledButton>
      <Modal opened={opened} onClose={close} title="意見回饋" centered>
        <Stack gap="sm">
          <Select label="類別" data={CATEGORIES} value={category}
            onChange={(v) => setCategory(v ?? "其他")} allowDeselect={false} />
          <Textarea label="內容" placeholder="想給我們的建議、遇到的問題…" minRows={4} autosize
            maxLength={2000} value={message} onChange={(e) => setMessage(e.currentTarget.value)} />
          {err && <Text c="danger.5" fz="sm">{err}</Text>}
          <Group justify="flex-end">
            <Button variant="subtle" color="gray" onClick={close}>取消</Button>
            <Button color="tangerine" loading={busy} disabled={!message.trim()} onClick={submit}>送出</Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
