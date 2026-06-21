import React from "react";
import ReactDOM from "react-dom/client";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GoogleOAuthProvider } from "@react-oauth/google";
import { BrowserRouter } from "react-router-dom";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles/global.css";
import { App } from "./App";
import { theme } from "./theme";
import { ResumeProvider } from "./state/resume";
import { AuthProvider } from "./state/auth";
import { AuthGate } from "./components/AuthGate";

const queryClient = new QueryClient();
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

const gated = (
  <AuthProvider>
    <AuthGate>
      <ResumeProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ResumeProvider>
    </AuthGate>
  </AuthProvider>
);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark" forceColorScheme="dark">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        {GOOGLE_CLIENT_ID ? (
          <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>{gated}</GoogleOAuthProvider>
        ) : (
          gated
        )}
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
