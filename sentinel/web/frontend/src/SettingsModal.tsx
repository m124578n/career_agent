import { Button, Modal, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { getSettings, putSettings, type Settings } from "./api";

export default function SettingsModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings, enabled: opened });
  const [companies, setCompanies] = useState("");
  const [keywords, setKeywords] = useState("");
  const [notifyTime, setNotifyTime] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (opened && settings.data) {
      setCompanies(settings.data.watched_companies.join("\n"));
      setKeywords(settings.data.watched_keywords.join("\n"));
      setNotifyTime(settings.data.notify_time ?? "");
    }
  }, [opened, settings.data]);

  async function save() {
    setErr(null);
    const payload: Settings = {
      watched_companies: companies.split("\n").map((s) => s.trim()).filter(Boolean),
      watched_keywords: keywords.split("\n").map((s) => s.trim()).filter(Boolean),
      notify_time: notifyTime.trim() === "" ? null : notifyTime.trim(),
    };
    const r = await putSettings(payload);
    if (!r.ok) { setErr("時間格式需為 HH:MM"); return; }
    qc.invalidateQueries({ queryKey: ["settings"] });
    qc.invalidateQueries({ queryKey: ["snapshot"] });
    onClose();
  }

  return (
    <Modal opened={opened} onClose={onClose} title="設定">
      <Stack>
        <Textarea label="關注公司（一行一個）" autosize minRows={3} value={companies} onChange={(e) => setCompanies(e.currentTarget.value)} />
        <Textarea label="職缺關鍵字（一行一個）" autosize minRows={3} value={keywords} onChange={(e) => setKeywords(e.currentTarget.value)} />
        <TextInput type="time" label="通知時間（HH:MM）" value={notifyTime} onChange={(e) => setNotifyTime(e.currentTarget.value)} />
        {err && <Text c="red" size="sm">{err}</Text>}
        <Button onClick={save}>儲存</Button>
      </Stack>
    </Modal>
  );
}
