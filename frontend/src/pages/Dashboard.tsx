import { Box, Button, Group, Stack, Text, Title } from "@mantine/core";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useResume } from "../state/resume";

export function Dashboard() {
  const { target } = useResume();
  const searchesQ = useQuery({ queryKey: ["searches"], queryFn: api.listSearches });
  const appsQ = useQuery({ queryKey: ["applications"], queryFn: api.listApplications });
  const quotaQ = useQuery({ queryKey: ["quota"], queryFn: api.quota });

  const hasResume = !!target?.resume_text && !!target?.target_title;
  const hasSearches = (searchesQ.data?.length ?? 0) > 0;
  const trackedCount = appsQ.data?.length ?? 0;
  const hasTracked = trackedCount > 0;
  const quota = quotaQ.data;

  // 下一步狀態機：依序判斷，命中即為當前下一步
  const next = !hasResume
    ? { to: "/resume", label: "履歷與目標", cta: "前往設定", desc: "先上傳履歷、填好目標職位，我幫你看亮點與可加強的地方。" }
    : !hasSearches
    ? { to: "/jobs", label: "職缺契合度", cta: "去找職缺", desc: "履歷準備好了！搜尋職缺，逐筆比對你的契合度。" }
    : !hasTracked
    ? { to: "/jobs", label: "職缺契合度", cta: "回到職缺", desc: "把有興趣、契合度高的職缺加入追蹤吧。" }
    : { to: "/applications", label: "追蹤清單", cta: "管理追蹤", desc: "在看板上更新投遞與面試進度。" };

  const steps = [
    { n: "01", to: "/resume", label: "履歷與目標", status: hasResume ? "已完成" : "待設定", done: hasResume },
    { n: "02", to: "/jobs", label: "職缺契合度", status: hasSearches ? "進行中" : "尚未開始", done: hasSearches },
    { n: "03", to: "/applications", label: "追蹤清單", status: hasTracked ? `${trackedCount} 筆` : "尚無", done: hasTracked },
  ];

  return (
    <Box p={{ base: "lg", md: 40 }} maw={1180} mx="auto">
      {/* 歡迎 + 狀態列 */}
      <Group justify="space-between" align="flex-end" mb={28} wrap="wrap">
        <Stack gap={6}>
          <span className="jt-eyebrow">總覽</span>
          <Title order={1} fz={{ base: 26, md: 32 }} fw={700} lts="-0.02em">
            歡迎回來 👋
          </Title>
        </Stack>
        <Group gap={24}>
          <div>
            <div className="jt-eyebrow">今日額度</div>
            <Text fz="lg" fw={600} ff="monospace" c="var(--jt-text)">
              {quota ? `${quota.used} / ${quota.limit}` : "—"}
            </Text>
          </div>
          <div>
            <div className="jt-eyebrow">追蹤中</div>
            <Text fz="lg" fw={600} ff="monospace" c="var(--jt-text)">
              {trackedCount}
            </Text>
          </div>
        </Group>
      </Group>

      {/* 你的下一步 */}
      <div className="jt-eyebrow" style={{ marginBottom: 10 }}>你的下一步</div>
      <div className="jt-panel" style={{ marginBottom: 28 }}>
        <div className="jt-panel-body">
          <Group justify="space-between" align="center" wrap="wrap" gap={16}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <Text fw={600} fz="md" mb={4} c="var(--jt-text)">
                {next.label}
              </Text>
              <Text fz="sm" c="dimmed" style={{ lineHeight: 1.6 }}>
                {next.desc}
              </Text>
            </div>
            <Button component={Link} to={next.to} color="tangerine" size="md">
              {next.cta} →
            </Button>
          </Group>
        </div>
      </div>

      {/* 求職旅程 */}
      <div className="jt-eyebrow" style={{ marginBottom: 10 }}>求職旅程</div>
      <Group gap={12} align="stretch" wrap="wrap">
        {steps.map((s) => {
          const active = s.to === next.to;
          return (
            <Link
              key={s.n}
              to={s.to}
              style={{ flex: "1 1 220px", minWidth: 200, textDecoration: "none", display: "block" }}
            >
              <div
                className="jt-panel"
                style={{ padding: 16, height: "100%", borderColor: active ? "var(--jt-teal)" : undefined }}
              >
                <Group gap={8} mb={6}>
                  <span
                    style={{
                      fontFamily: "var(--mantine-font-family-monospace)",
                      fontSize: 12,
                      color: s.done ? "var(--jt-teal)" : "var(--jt-dim)",
                    }}
                  >
                    {s.n}
                  </span>
                  <Text fw={600} fz="sm" c="var(--jt-text)">
                    {s.label}
                  </Text>
                </Group>
                <Text fz="xs" c={s.done ? "teal" : "dimmed"}>
                  {s.status}
                </Text>
              </div>
            </Link>
          );
        })}
      </Group>
    </Box>
  );
}
