// 打 backend 的薄封裝。所有路徑走 /api（由 Vite proxy 轉到 FastAPI）。

import type {
  JobMatch,
  ResumeDiagnosis,
  ResumeTarget,
  UsageSummary,
} from "../types";

export interface AnalyzeRequest {
  keyword: string;
  target: ResumeTarget;
  limit?: number;
  page?: number;
}

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, init);
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
};
