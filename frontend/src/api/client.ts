// 打 backend 的薄封裝。所有路徑走 BASE（dev 走 Vite proxy /api；prod 用 VITE_API_BASE_URL）。

import type {
  Application,
  ApplicationStatus,
  JobMatch,
  QuotaInfo,
  ResumeDiagnosis,
  ResumeTarget,
  SearchRun,
  UsageSummary,
} from "../types";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";
const TOKEN_KEY = "jobtracker.token";

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
  // 以 localStorage 為準，避免任何 render 時序造成漏帶 token
  const token = authToken ?? localStorage.getItem(TOKEN_KEY);
  if (token) headers.Authorization = `Bearer ${token}`;

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
  createSearch: (req: { keyword: string; target: ResumeTarget }) =>
    request<{ search_id: string; matches: JobMatch[] }>("/jobs/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  nextBatch: (searchId: string) =>
    request<JobMatch[]>(`/jobs/searches/${searchId}/next`, { method: "POST" }),
  listSearches: () => request<SearchRun[]>("/jobs/searches"),
  searchMatches: (searchId: string) =>
    request<JobMatch[]>(`/jobs/searches/${searchId}/matches`),
  deleteSearch: (searchId: string) =>
    request<{ ok: boolean }>(`/jobs/searches/${searchId}`, { method: "DELETE" }),
  coverLetter: (req: { search_id: string; job_id: string }) =>
    request<{ cover_letter: string }>(
      `/jobs/searches/${req.search_id}/cover-letter`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: req.job_id }),
      }
    ),
  addApplication: (req: { search_id: string; job_id: string }) =>
    request<Application>("/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
  listApplications: () => request<Application[]>("/applications"),
  updateApplicationStatus: (jobId: string, status: ApplicationStatus) =>
    request<Application>(`/applications/${jobId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  removeApplication: (jobId: string) =>
    request<{ ok: boolean }>(`/applications/${jobId}`, { method: "DELETE" }),
  usage: () => request<UsageSummary>("/usage"),
  globalUsage: () => request<UsageSummary>("/usage/global"),
  quota: () => request<QuotaInfo>("/usage/quota"),
};
