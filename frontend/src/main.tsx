import React from "react";
import ReactDOM from "react-dom/client";
import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles/global.css";
import { App } from "./App";
import { theme } from "./theme";
import { ResumeProvider } from "./state/resume";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <MantineProvider theme={theme} defaultColorScheme="dark" forceColorScheme="dark">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <ResumeProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ResumeProvider>
      </QueryClientProvider>
    </MantineProvider>
  </React.StrictMode>,
);
