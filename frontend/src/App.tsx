import { AppShell, NavLink, Title } from "@mantine/core";
import { Navigate, Route, Routes, NavLink as RouterNavLink } from "react-router-dom";
import { ResumeSetup } from "./pages/ResumeSetup";
import { JobList } from "./pages/JobList";

const NAV = [
  { to: "/resume", label: "履歷與目標" },
  { to: "/jobs", label: "職缺契合度" },
];

export function App() {
  return (
    <AppShell navbar={{ width: 220, breakpoint: "sm" }} padding="md">
      <AppShell.Navbar p="md">
        <Title order={4} mb="md">
          104 Job Tracker
        </Title>
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            component={RouterNavLink}
            to={item.to}
            label={item.label}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Routes>
          <Route path="/" element={<Navigate to="/resume" replace />} />
          <Route path="/resume" element={<ResumeSetup />} />
          <Route path="/jobs" element={<JobList />} />
        </Routes>
      </AppShell.Main>
    </AppShell>
  );
}
