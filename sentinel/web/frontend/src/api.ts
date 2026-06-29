export interface Viewer { company: string; job_title: string; viewed_at: string; watched: boolean }
export interface Application { job_id: string; company: string; title: string; status: string; applied_at: string; watched: boolean }
export interface Message { thread_id: string; company: string; last_message: string; has_interview_invite: boolean; watched: boolean }
export interface SnapshotResp {
  run_at: string | null;
  viewers: Viewer[];
  applications: Application[];
  messages: Message[];
  digest: string;
  failed_readers: string[];
}
export interface StatusResp { running: boolean; last_run: string | null; last_error: string | null; last_failed_readers: string[] }

export async function getSnapshot(): Promise<SnapshotResp> {
  const r = await fetch("/api/snapshot");
  return r.json();
}
export async function getStatus(): Promise<StatusResp> {
  const r = await fetch("/api/status");
  return r.json();
}
export async function startScrape(): Promise<{ status: string }> {
  const r = await fetch("/api/scrape", { method: "POST" });
  return r.json();
}

export interface Settings { watched_companies: string[]; watched_keywords: string[]; notify_time: string | null }

export async function getSettings(): Promise<Settings> {
  const r = await fetch("/api/settings");
  return r.json();
}

export async function putSettings(s: Settings): Promise<Response> {
  return fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(s),
  });
}
