import { Anchor, AppShell, Avatar, Group, NavLink, Stack, Text } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import {
  Navigate,
  Route,
  Routes,
  NavLink as RouterNavLink,
} from "react-router-dom";
import { api } from "./api/client";
import { useAuth } from "./state/auth";
import { ResumeSetup } from "./pages/ResumeSetup";
import { JobList } from "./pages/JobList";
import { Applications } from "./pages/Applications";

const NAV = [
  { to: "/resume", label: "履歷與目標", tag: "01" },
  { to: "/jobs", label: "職缺契合度", tag: "02" },
  { to: "/applications", label: "追蹤清單", tag: "03" },
];

export function App() {
  return (
    <AppShell navbar={{ width: 232, breakpoint: "sm" }} padding={0}>
      <AppShell.Navbar
        p="md"
        style={{
          background: "var(--jt-panel)",
          borderColor: "var(--jt-border)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Stack gap={2} mb="xl" px={6} pt={4}>
          <span className="jt-brand">
            JobTracker<span className="dot">.</span>
          </span>
          <span className="jt-brandtag">AI 求職指揮艙</span>
        </Stack>

        <Stack gap={4}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              component={RouterNavLink}
              to={item.to}
              label={item.label}
              leftSection={
                <span
                  style={{
                    fontFamily: "var(--mantine-font-family-monospace)",
                    fontSize: 11,
                    color: "var(--jt-dim)",
                  }}
                >
                  {item.tag}
                </span>
              }
              styles={{
                root: { borderRadius: 8 },
                label: { fontSize: 14, fontWeight: 500 },
              }}
            />
          ))}
        </Stack>

        <div style={{ marginTop: "auto" }}>
          <AccountFooter />
        </div>
      </AppShell.Navbar>

      <AppShell.Main style={{ minHeight: "100dvh" }}>
        <Routes>
          <Route path="/" element={<Navigate to="/resume" replace />} />
          <Route path="/resume" element={<ResumeSetup />} />
          <Route path="/jobs" element={<JobList />} />
          <Route path="/applications" element={<Applications />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}

function AccountFooter() {
  const { enabled, user, logout } = useAuth();
  const { data: quota } = useQuery({
    queryKey: ["quota"],
    queryFn: api.quota,
    refetchInterval: 15000,
  });
  const { data: usage } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    refetchInterval: 15000,
  });
  const { data: globalUsage } = useQuery({
    queryKey: ["usage-global"],
    queryFn: api.globalUsage,
    refetchInterval: 15000,
    enabled: !!quota?.is_admin, // 僅 admin 撈全站
  });

  return (
    <Stack
      gap={12}
      style={{ borderTop: "1px solid var(--jt-border)", paddingTop: 12 }}
      px={6}
    >
      {/* 今日額度 */}
      <div>
        <div className="jt-eyebrow">今日額度</div>
        <div
          style={{
            fontFamily: "var(--mantine-font-family-monospace)",
            fontSize: 17,
            fontWeight: 600,
            color: "var(--jt-text)",
            marginTop: 4,
          }}
        >
          {quota ? `${quota.used} / ${quota.limit}` : "—"}
        </div>
        <div style={{ fontSize: 11, color: "var(--jt-dim)" }}>
          剩餘 {quota?.remaining ?? "—"} 次（每日重置）
        </div>
      </div>

      {/* 個人 token；admin 另看全站 */}
      <div>
        <Text fz={11} c="dimmed" ff="monospace">
          我的 {(usage?.total_tokens ?? 0).toLocaleString()} tokens
        </Text>
        {quota?.is_admin && (
          <Text fz={11} c="tangerine.5" ff="monospace">
            全站 {(globalUsage?.total_tokens ?? 0).toLocaleString()} tokens
          </Text>
        )}
      </div>

      {/* 使用者 + 登出 */}
      {enabled && user && (
        <Group gap={8} wrap="nowrap">
          <Avatar src={user.picture} size={26} radius="xl">
            {user.email[0]?.toUpperCase()}
          </Avatar>
          <div style={{ minWidth: 0, flex: 1 }}>
            <Text fz={12} truncate c="var(--jt-text)">
              {user.name ?? user.email}
            </Text>
            <Anchor fz={11} c="tangerine.5" onClick={logout} style={{ cursor: "pointer" }}>
              登出
            </Anchor>
          </div>
        </Group>
      )}
    </Stack>
  );
}
