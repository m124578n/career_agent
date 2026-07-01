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
