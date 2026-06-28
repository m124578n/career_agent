export interface Viewer { company: string; job_title: string; viewed_at: string }
export interface Application { job_id: string; company: string; title: string; status: string; applied_at: string }
export interface Message { thread_id: string; company: string; last_message: string; has_interview_invite: boolean }
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
