import { Box, Group, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

/** 統一頁面容器：置中＋一致的寬度系統（md=閱讀/表單頁、lg=清單/雙欄頁） */
export function PageContainer({ children, size = "md" }: {
  children: ReactNode; size?: "md" | "lg";
}) {
  return (
    <Box maw={size === "lg" ? 1060 : 860} mx="auto" px={40} py={32}>
      {children}
    </Box>
  );
}

export function PageHeader({ title, subtitle, action }: {
  title: string; subtitle?: string; action?: ReactNode;
}) {
  return (
    <Group justify="space-between" align="flex-end" mb="xl">
      <Stack gap={4}>
        <Title order={2} style={{ letterSpacing: "-0.5px" }}>{title}</Title>
        {subtitle && <Text size="sm" c="dimmed">{subtitle}</Text>}
      </Stack>
      {action}
    </Group>
  );
}

export function Kpi({ value, label, suffix }: {
  value: ReactNode; label: string; suffix?: ReactNode;
}) {
  return (
    <div>
      <div style={{
        fontFamily: "'Space Grotesk', sans-serif", fontSize: 52, fontWeight: 700,
        letterSpacing: "-3px", lineHeight: 1, color: "var(--mantine-color-dark-0)",
        display: "flex", alignItems: "baseline", gap: 8,
      }}>
        <span>{value}</span>
        {suffix}
      </div>
      <Text size="xs" c="dimmed" mt={8} style={{ letterSpacing: 2 }}>{label}</Text>
    </div>
  );
}
