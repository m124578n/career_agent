import { Stepper } from "@mantine/core";

const STEPS = [
  { key: "establish", label: "建立連線" },
  { key: "viewers", label: "誰看過我" },
  { key: "applications", label: "應徵" },
  { key: "messages", label: "訊息" },
  { key: "interviews", label: "面試" },
  { key: "digest", label: "整理" },
];

export default function ScrapeStepper({ phase }: { phase: string }) {
  const active = STEPS.findIndex((s) => s.key === phase);
  if (active < 0) return null; // phase 空或不在清單 → 不顯示（閒置/同步爬蟲不觸發）
  return (
    <Stepper active={active} size="xs" p="md" pb={0} iconSize={22}>
      {STEPS.map((s) => (
        <Stepper.Step key={s.key} label={s.label} />
      ))}
    </Stepper>
  );
}
