import { Group, Loader, Text } from "@mantine/core";
import { useElapsed } from "./useElapsed";

/** 單次等待計時提示：active 時顯示「{label}…（已 N 秒）」。hook 必在 return 前呼叫。 */
export default function BusyHint({ active, label }: { active: boolean; label: string }) {
  const n = useElapsed(active);
  if (!active) return null;
  return (
    <Group gap={6} c="dimmed" mt={4}>
      <Loader size="xs" />
      <Text size="xs">{label}…（已 {n} 秒）</Text>
    </Group>
  );
}
