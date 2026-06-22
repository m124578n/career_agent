"""API 與資料層共用的 Pydantic 模型。對應前端 TS 型別。"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


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
    """一筆 104 職缺（搜尋列表層級）。"""

    job_id: str
    code: str = Field(description="職缺短碼，詳情 API 用（url 末段）")
    title: str
    company: str
    url: str
    salary: str | None = None
    description: str = ""
    crawled_at: datetime = Field(default_factory=_utcnow)


class JobDetail(BaseModel):
    """職缺詳情（詳情 API，含完整 JD 與條件需求，供契合度分析用）。"""

    description: str = Field(description="完整職缺描述")
    salary: str = ""
    location: str = ""
    work_exp: str = Field(default="", description="工作經驗需求")
    education: str = ""
    majors: list[str] = Field(default_factory=list, description="科系需求")
    specialties: list[str] = Field(default_factory=list, description="專長/技能")


class MatchAnalysis(BaseModel):
    """LLM 對單筆職缺的契合度分析輸出（結構化輸出 schema）。"""

    score: int = Field(ge=0, le=100, description="契合度 0~100")
    reasons: list[str] = Field(description="契合的理由")
    gaps: list[str] = Field(description="待補強/缺口")


class JobMatch(BaseModel):
    """職缺契合度分析（M4），= 職缺 + LLM 分析 + 規則判斷。"""

    job: Job
    score: float = Field(ge=0, le=100, description="契合度 0~100")
    reasons: list[str]
    gaps: list[str]
    requires_external_apply: bool = False
    cover_letter: str | None = None  # 已生成的求職信（M5），有值代表寫過


class SearchRun(BaseModel):
    """一次「爬取並分析」的搜尋紀錄（歷史）。"""

    search_id: str
    user: str
    keyword: str
    target: ResumeTarget
    created_at: datetime = Field(default_factory=_utcnow)
    next_offset: int = 0  # 下一批的 job 列表起點
    count: int = 0         # 累積成功分析筆數


class ApplicationStatus(str, Enum):
    TO_APPLY = "to_apply"
    APPLIED = "applied"
    INTERVIEWING = "interviewing"
    OFFER = "offer"
    CLOSED = "closed"


class ApplicationEvent(BaseModel):
    """追蹤時間軸上的一個事件（本期只記狀態變更）。"""

    ts: datetime = Field(default_factory=_utcnow)
    type: str
    note: str = ""


class Application(BaseModel):
    """求職追蹤清單的一筆（以 user|job_id 去重）。"""

    user: str
    job_id: str
    job: Job                       # 加入當下的職缺快照
    source_search_id: str          # 從哪筆 search 加入
    cover_letter: str | None = None  # 加入當下的求職信快照
    status: ApplicationStatus = ApplicationStatus.TO_APPLY
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    events: list[ApplicationEvent] = Field(default_factory=list)
