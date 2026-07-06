from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class Viewer(BaseModel):
    company: str
    job_title: str
    viewed_at: str
    raw: dict = Field(default_factory=dict)

    @property
    def key(self) -> tuple[str, str]:
        return (self.company, self.job_title)


class Application(BaseModel):
    job_id: str
    company: str
    title: str
    status: str
    applied_at: str
    raw: dict = Field(default_factory=dict)


class Message(BaseModel):
    thread_id: str
    company: str
    last_message: str
    has_interview_invite: bool = False
    invite_date: str | None = None
    raw: dict = Field(default_factory=dict)


class Snapshot(BaseModel):
    viewers: list[Viewer] = Field(default_factory=list)
    applications: list[Application] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    interviews: list["Interview"] = Field(default_factory=list)


class StatusChange(BaseModel):
    application: Application
    old_status: str
    new_status: str


class Diff(BaseModel):
    new_viewers: list[Viewer] = Field(default_factory=list)
    status_changes: list[StatusChange] = Field(default_factory=list)
    new_messages: list[Message] = Field(default_factory=list)
    new_invites: list[Message] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.new_viewers or self.status_changes
            or self.new_messages or self.new_invites
        )


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Settings(BaseModel):
    watched_companies: list[str] = Field(default_factory=list)
    watched_keywords: list[str] = Field(default_factory=list)
    notify_time: str | None = None

    @field_validator("notify_time")
    @classmethod
    def _check_time(cls, v: str | None) -> str | None:
        if v is not None and not _TIME_RE.match(v):
            raise ValueError("notify_time 需為 HH:MM")
        return v


class ResumeDiagnosis(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)


class ResumeState(BaseModel):
    resume_text: str = ""
    target_title: str = ""
    expected_salary: int | None = None
    diagnosis: ResumeDiagnosis | None = None
    source: str = ""   # "" | "upload" | "104"


class JobDetail(BaseModel):
    title: str = ""
    company: str = ""
    salary: str = ""
    location: str = ""
    description: str = ""
    work_exp: str = ""
    education: str = ""
    majors: list[str] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        try:
            n = int(round(float(v)))
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, n))


class RecommendedJob(BaseModel):
    code: str
    url: str
    title: str = ""
    company: str = ""
    salary: str = ""
    is_watched: bool = False


class ChangeCounts(BaseModel):
    new_viewers: int = 0
    status_changes: int = 0
    new_messages: int = 0
    new_invites: int = 0

    @property
    def total(self) -> int:
        return self.new_viewers + self.status_changes + self.new_messages + self.new_invites

    @classmethod
    def from_diff(cls, d: "Diff") -> "ChangeCounts":
        return cls(
            new_viewers=len(d.new_viewers),
            status_changes=len(d.status_changes),
            new_messages=len(d.new_messages),
            new_invites=len(d.new_invites),
        )


class Interview(BaseModel):
    company: str = ""
    job_title: str = ""
    when: str = ""
    location: str = ""
    status: int | None = None
    job_url: str = ""
    raw: dict = Field(default_factory=dict)


class DismissedInterviews(BaseModel):
    keys: list[str] = Field(default_factory=list)


def interview_key(iv: "Interview") -> str:
    """面試的跨抓取穩定鍵（隱藏/還原用）。"""
    return f"{iv.company}|{iv.job_title}|{iv.when}"


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatState(BaseModel):
    summary: str = ""  # 更早對話的壓縮摘要
    messages: list[ChatMessage] = Field(default_factory=list)


class JobPreferences(BaseModel):
    target_title: str = ""
    expected_salary: int | None = None
    locations: list[str] = Field(default_factory=list)   # 想要的工作地點
    conditions: list[str] = Field(default_factory=list)  # 軟條件
    avoid: list[str] = Field(default_factory=list)       # 避雷條件


class TrackedJob(BaseModel):
    code: str
    company: str = ""
    title: str = ""
    url: str = ""
    salary: str = ""
    state: str = "interested"   # interested|matched|tailored|offer|rejected
    match_score: int | None = None
    match_json: str = ""
    tailor_json: str = ""
    created_at: str = ""
    updated_at: str = ""


class PipelineJob(BaseModel):
    """合併引擎輸出的統一 DTO（前端據 state 分組渲染）。"""
    key: str                    # code；interview 無 code 時退回 company|job_title|when
    code: str = ""
    company: str = ""
    title: str = ""
    state: str = "interested"   # 有效狀態
    url: str = ""
    salary: str = ""
    match_score: int | None = None
    # 已投遞側（來自 applications）
    status: str = ""
    applied_at: str = ""
    # 面試側（來自 interviews）
    when: str = ""
    location: str = ""
    gcal_link: str = ""
    interview_key: str = ""
    dismissed: bool = False
    # 連結與旗標
    company_url: str = ""
    job_url: str = ""
    thread_url: str = ""
    watched: bool = False


class MemoryFact(BaseModel):
    text: str
    created_at: str = ""


class MemoryState(BaseModel):
    facts: list[MemoryFact] = Field(default_factory=list)


class SuggestedUpdate(BaseModel):
    field: str
    op: str = "set"  # set | replace_snippet | append_section | remember
    value: str | int | list[str] | None = None
    old: str | None = None  # replace_snippet 專用
    new: str | None = None  # replace_snippet 專用


class ResearchSource(BaseModel):
    title: str = ""
    url: str = ""


class CompanyResearch(BaseModel):
    company: str = ""
    summary: str = ""
    pros: list[str] = Field(default_factory=list)
    cons: list[str] = Field(default_factory=list)
    salary_notes: str = ""
    interview_notes: str = ""
    risk_level: str = "mid"  # low | mid | high
    sources: list[ResearchSource] = Field(default_factory=list)
    researched_at: str = ""  # ISO

    @field_validator("risk_level", mode="before")
    @classmethod
    def _check_risk(cls, v):
        return v if v in ("low", "mid", "high") else "mid"


class TailoredApplication(BaseModel):
    job_title: str = ""
    company: str = ""
    resume_tips: list[str] = Field(default_factory=list)
    resume_adjustments: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    cover_letter: str = ""


class Resume104Block(BaseModel):
    id: str
    label: str
    text: str = ""
    is_pii: bool = False
    completed: bool = False


class Resume104(BaseModel):
    vno: str = ""
    progress: int = 0
    blocks: list[Resume104Block] = Field(default_factory=list)
