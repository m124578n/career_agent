export interface Viewer { company: string; job_title: string; viewed_at: string; watched: boolean; company_url: string }
export interface Application { job_id: string; company: string; title: string; status: string; applied_at: string; watched: boolean; company_url: string; job_url: string }
export interface Message { thread_id: string; company: string; last_message: string; has_interview_invite: boolean; watched: boolean; company_url: string; thread_url: string }
export interface Interview { company: string; job_title: string; when: string; location: string; job_url: string; gcal_link: string; key: string; dismissed: boolean; company_url: string; thread_url: string }
export interface SnapshotResp {
  run_at: string | null;
  viewers: Viewer[];
  applications: Application[];
  messages: Message[];
  interviews: Interview[];
  digest: string;
  failed_readers: string[];
}
export interface ChangeCounts { new_viewers: number; status_changes: number; new_messages: number; new_invites: number }
export interface StatusResp { running: boolean; last_run: string | null; last_error: string | null; last_failed_readers: string[]; last_change_counts: ChangeCounts }

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

export interface ResumeDiagnosis { strengths: string[]; gaps: string[] }
export interface ResumeState {
  has_resume: boolean;
  chars: number;
  target_title: string;
  expected_salary: number | null;
  diagnosis: ResumeDiagnosis | null;
}

export async function getResume(): Promise<ResumeState> {
  const r = await fetch("/api/resume");
  return r.json();
}

export async function uploadResume(file: File): Promise<Response> {
  const fd = new FormData();
  fd.append("file", file);
  return fetch("/api/resume/upload", { method: "POST", body: fd });
}

export async function diagnoseResume(target_title: string, expected_salary: number | null): Promise<Response> {
  return fetch("/api/resume/diagnose", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_title, expected_salary }),
  });
}

export interface MatchResult {
  title: string;
  company: string;
  salary: string;
  score: number;
  reasons: string[];
  gaps: string[];
}

export async function matchJob(job_url: string): Promise<Response> {
  return fetch("/api/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_url }),
  });
}

export interface RecommendedJob {
  code: string;
  url: string;
  title: string;
  company: string;
  salary: string;
  is_watched: boolean;
}

export async function getRecommend(): Promise<Response> {
  return fetch("/api/recommend");
}

export async function searchJobs(kw: string): Promise<Response> {
  return fetch(`/api/search?kw=${encodeURIComponent(kw)}`);
}

export interface ScheduleState { due: boolean; notify_time: string | null; last_prompted_date: string | null }

export async function getSchedule(): Promise<ScheduleState> {
  const r = await fetch("/api/schedule");
  return r.json();
}

export async function ackSchedule(): Promise<void> {
  await fetch("/api/schedule/ack", { method: "POST" });
}

export interface ChatMsg { role: string; content: string }
export interface SuggestedUpdate {
  field: string;
  op: string;
  value: string | number | string[] | null;
  old: string | null;
  new: string | null;
}
export interface MemoryFact { text: string; created_at: string }
export interface ChatHistory { summary: string; messages: ChatMsg[]; memory: MemoryFact[] }

export async function getChat(): Promise<ChatHistory> {
  const r = await fetch("/api/chat");
  return r.json();
}

export function sendChat(message: string): Promise<Response> {
  return fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function applyUpdate(u: SuggestedUpdate): Promise<Response> {
  return fetch("/api/chat/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(u),
  });
}

export async function clearChat(): Promise<void> {
  await fetch("/api/chat", { method: "DELETE" });
}

export async function deleteMemory(index: number): Promise<void> {
  await fetch(`/api/memory/${index}`, { method: "DELETE" });
}

// 解析 SSE 串流（event/data 區塊以空行分隔；處理跨 chunk 邊界）
export async function readSse(
  resp: Response,
  onEvent: (event: string, data: any) => void,
): Promise<void> {
  const reader = resp.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    for (;;) {
      const i = buf.indexOf("\n\n");
      if (i === -1) break;
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const ev = block.match(/^event: (.+)$/m);
      const data = block.match(/^data: (.+)$/m);
      if (ev && data) onEvent(ev[1], JSON.parse(data[1]));
    }
  }
}

export async function dismissInterview(key: string): Promise<void> {
  await fetch("/api/interviews/dismiss", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
}

export async function restoreInterview(key: string): Promise<void> {
  await fetch("/api/interviews/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
}
