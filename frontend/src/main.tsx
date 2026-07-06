import React, { Suspense, lazy } from "react";
import ReactDOM from "react-dom/client";
import { Center, Loader, MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles/global.css";
import { GatedLayout } from "./App";
import { theme } from "./theme";
import { ResumeProvider } from "./state/resume";
import { AuthProvider, useAuth } from "./state/auth";
import { AuthGate } from "./components/AuthGate";

// 路由層拆包：各頁按需載入，首屏只下載必要的程式碼
const About = lazy(() => import("./pages/About").then((m) => ({ default: m.About })));
const SelfHost = lazy(() => import("./pages/SelfHost").then((m) => ({ default: m.SelfHost })));
const ResumeSetup = lazy(() => import("./pages/ResumeSetup").then((m) => ({ default: m.ResumeSetup })));
const JobList = lazy(() => import("./pages/JobList").then((m) => ({ default: m.JobList })));
const Applications = lazy(() => import("./pages/Applications").then((m) => ({ default: m.Applications })));
const Landing = lazy(() => import("./pages/Landing").then((m) => ({ default: m.Landing })));
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));

function PageFallback() {
  return (
    <Center mih="100dvh">
      <Loader color="tangerine" />
    </Center>
  );
}

// 首頁決策：未登入 → Landing；已登入（或免登入）→ 轉 /home
function RootRoute() {
  const { enabled, token } = useAuth();
  if (enabled && !token) return <Landing />;
  return <Navigate to="/home" replace />;
}

const queryClient = new QueryClient();
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

function GatedShell() {
  return (
    <AuthGate>
      <ResumeProvider>
        <GatedLayout />
      </ResumeProvider>
    </AuthGate>
  );
}

const app = (
  <AuthProvider>
    <BrowserRouter>
      <Suspense fallback={<PageFallback />}>
        <Routes>
          <Route path="/about" element={<About />} />
          <Route path="/self-host" element={<SelfHost />} />
          <Route path="/" element={<RootRoute />} />
          <Route element={<GatedShell />}>
            <Route path="/home" element={<Dashboard />} />
            <Route path="/resume" element={<ResumeSetup />} />
            <Route path="/jobs" element={<JobList />} />
            <Route path="/applications" element={<Applications />} />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  </AuthProvider>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark" forceColorScheme="dark">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        {GOOGLE_CLIENT_ID ? (
          <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{app}</GoogleOAuthProvider>
        ) : (
          app
        )}
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
