// 對應 backend/src/job_tracker/schemas。手動保持同步。

export interface ResumeTarget {
  target_title: string;
  expected_salary: number | null;
  resume_text: string;
}

export interface ResumeDiagnosis {
  strengths: string[];
  gaps: string[];
}

export interface UsageSummary {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  by_model: Record<string, number>;
}

export interface QuotaInfo {
  used: number;
  limit: number;
  remaining: number;
  is_admin: boolean;
}

export interface Job {
  job_id: string;
  code: string;
  title: string;
  company: string;
  url: string;
  salary?: string | null;
  description: string;
  crawled_at: string;
}

export interface JobMatch {
  job: Job;
  score: number;
  reasons: string[];
  gaps: string[];
  benefits: string[];
  requires_external_apply: boolean;
  cover_letter?: string | null;
  status: "candidate" | "pending" | "done" | "failed";
  relevant: boolean;
}

export interface SearchRun {
  search_id: string;
  user: string;
  keyword: string;
  target: ResumeTarget;
  created_at: string;
  next_page: number;
  area: string | null;
  count: number;
}

export type ApplicationStatus =
  | "to_apply"
  | "applied"
  | "interviewing"
  | "offer"
  | "closed";

export interface ApplicationEvent {
  ts: string;
  type: string;
  note: string;
}

export interface OfferInfo {
  salary?: string | null;
  level?: string | null;
  start_date?: string | null;
  accepted?: boolean | null;
  note?: string | null;
}

export interface Application {
  user: string;
  job_id: string;
  job: Job;
  source_search_id: string;
  cover_letter?: string | null;
  status: ApplicationStatus;
  created_at: string;
  updated_at: string;
  events: ApplicationEvent[];
  offer?: OfferInfo | null;
}
