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
  requires_external_apply: boolean;
}
