import { useEffect, useState } from "react";
import { Group, Loader, Stack, Text } from "@mantine/core";

/**
 * 輕量「進度」顯示：階段文字依序出現（像終端機序列）+ 經過秒數。
 * 不是真實後端進度，是依時間推進的模擬，讓使用者知道在跑、別關視窗。
 */
export function AnalyzingSteps({
  steps,
  intervalSec = 5,
}: {
  steps: string[];
  intervalSec?: number;
}) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const t0 = Date.now();
    const id = setInterval(
      () => setElapsed(Math.floor((Date.now() - t0) / 1000)),
      250,
    );
    return () => clearInterval(id);
  }, []);

  const shown = Math.min(steps.length, Math.floor(elapsed / intervalSec) + 1);
  const current = shown - 1;

  return (
    <Stack gap={10} py={24} px={6}>
      {steps.slice(0, shown).map((label, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <Group key={i} gap={10} wrap="nowrap">
            <span
              style={{
                fontFamily: "var(--mantine-font-family-monospace)",
                width: 14,
                color: done ? "var(--jt-teal)" : "var(--jt-accent)",
              }}
            >
              {done ? "✓" : "▸"}
            </span>
            <Text
              fz="sm"
              style={{
                color: done ? "var(--jt-muted)" : "var(--jt-text)",
              }}
            >
              {label}
            </Text>
            {active && <Loader size={12} color="tangerine" />}
          </Group>
        );
      })}
      <Text fz="xs" c="dimmed" ff="monospace" pl={24}>
        {elapsed}s · 請勿關閉視窗
      </Text>
    </Stack>
  );
}
