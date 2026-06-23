import React from "react";
import ReactDOM from "react-dom/client";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles/global.css";
import { GatedLayout } from "./App";
import { About } from "./pages/About";
import { ResumeSetup } from "./pages/ResumeSetup";
import { JobList } from "./pages/JobList";
import { Applications } from "./pages/Applications";
import { theme } from "./theme";
import { ResumeProvider } from "./state/resume";
import { AuthProvider } from "./state/auth";
import { AuthGate } from "./components/AuthGate";

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
      <Routes>
        <Route path="/about" element={<About />} />
        <Route element={<GatedShell />}>
          <Route path="/" element={<Navigate to="/resume" replace />} />
          <Route path="/resume" element={<ResumeSetup />} />
          <Route path="/jobs" element={<JobList />} />
          <Route path="/applications" element={<Applications />} />
        </Route>
      </Routes>
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
