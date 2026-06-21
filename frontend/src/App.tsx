import { AppShell, NavLink, Stack } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import {
  Navigate,
  Route,
  Routes,
  NavLink as RouterNavLink,
} from "react-router-dom";
import { api } from "./api/client";
import { ResumeSetup } from "./pages/ResumeSetup";
import { JobList } from "./pages/JobList";

const NAV = [
  { to: "/resume", label: "履歷與目標", tag: "01" },
  { to: "/jobs", label: "職缺契合度", tag: "02" },
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
          <UsageFooter />
        </div>
      </AppShell.Navbar>

      <AppShell.Main style={{ minHeight: "100dvh" }}>
        <Routes>
          <Route path="/" element={<Navigate to="/resume" replace />} />
          <Route path="/resume" element={<ResumeSetup />} />
          <Route path="/jobs" element={<JobList />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}

function UsageFooter() {
  const { data } = useQuery({
    queryKey: ["usage"],
    queryFn: api.usage,
    refetchInterval: 15000,
  });
  return (
    <div
      style={{
        borderTop: "1px solid var(--jt-border)",
        paddingTop: 12,
        paddingLeft: 6,
      }}
    >
      <div className="jt-eyebrow">TOKENS 用量</div>
      <div
        style={{
          fontFamily: "var(--mantine-font-family-monospace)",
          fontSize: 18,
          fontWeight: 600,
          color: "var(--jt-text)",
          marginTop: 4,
        }}
      >
        {(data?.total_tokens ?? 0).toLocaleString()}
      </div>
      <div style={{ fontSize: 11, color: "var(--jt-dim)" }}>
        {data?.calls ?? 0} 次呼叫
      </div>
    </div>
  );
}
