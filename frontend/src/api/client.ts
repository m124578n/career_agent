// 打 backend 的薄封裝。所有路徑走 BASE（dev 走 Vite proxy /api；prod 用 VITE_API_BASE_URL）。

import type {
  JobMatch,
  QuotaInfo,
  ResumeDiagnosis,
  ResumeTarget,
  UsageSummary,
} from "../types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

let authToken: string | null = null;
export function setAuthToken(token: string | null) {
  authToken = token;
}

let onUnauthorized: (() => void) | null = null;
export function setOnUnauthorized(fn: (() => void) | null) {
  onUnauthorized = fn;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;

  const resp = await fetch(`${BASE}${path}`, { ...init, headers });
  if (resp.status === 401) {
    onUnauthorized?.();
    throw new Error("未授權，請重新登入");
  }
  if (!resp.ok) {
    throw new Error(`API ${resp.status}: ${await resp.text()}`);
  }
  return resp.json() as Promise<T>;
}

export interface AnalyzeRequest {
  keyword: string;
  target: ResumeTarget;
  limit?: number;
  page?: number;
}

export const api = {
  parseResume: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ text: string }>("/resumes/parse", {
      method: "POST",
      body: form,
    });
  },
  diagnose: (target: ResumeTarget) =>
    request<ResumeDiagnosis>("/resumes/diagnose", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(target),
    }),
  listMatches: () => request<JobMatch[]>("/jobs/matches"),
  analyzeJobs: (req: AnalyzeRequest) =>
    request<JobMatch[]>("/jobs/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  coverLetter: (req: { target: ResumeTarget; job_id: string }) =>
    request<{ cover_letter: string }>("/applications/cover-letter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  usage: () => request<UsageSummary>("/usage"),
  globalUsage: () => request<UsageSummary>("/usage/global"),
  quota: () => request<QuotaInfo>("/usage/quota"),
};
