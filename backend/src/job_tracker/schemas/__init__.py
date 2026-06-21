"""API 與資料層共用的 Pydantic 模型。對應前端 TS 型別。"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ResumeTarget(BaseModel):
    """履歷 + 目標設定（M1）。"""

    target_title: str = Field(description="目標職位")
    expected_salary: int | None = Field(default=None, description="期望月薪（TWD）")
    resume_text: str = Field(description="解析後的履歷純文字")


class ResumeDiagnosis(BaseModel):
    """履歷診斷結果（M2）。"""

    strengths: list[str]
    gaps: list[str]


class Job(BaseModel):
    """一筆 104 職缺。"""

    job_id: str
    title: str
    company: str
    url: str
    salary: str | None = None
    description: str = ""
    crawled_at: datetime = Field(default_factory=datetime.utcnow)


class JobMatch(BaseModel):
    """職缺契合度分析（M4）。"""

    job: Job
    score: float = Field(ge=0, le=100, description="契合度 0~100")
    reasons: list[str]
    gaps: list[str]
    requires_external_apply: bool = False


class ApplicationStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    EXTERNAL_REQUIRED = "external_required"
    SKIPPED = "skipped"


class Application(BaseModel):
    """投遞紀錄。"""

    job_id: str
    status: ApplicationStatus = ApplicationStatus.PENDING
    cover_letter: str | None = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
