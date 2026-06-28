from __future__ import annotations

from pydantic import BaseModel, Field


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
