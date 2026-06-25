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
    benefits: list[str] = Field(
        default_factory=list, description="JD 明確提到的福利，標籤化（≤8字，最多6項）"
    )


class JobMatch(BaseModel):
    """職缺契合度分析。candidate/pending 階段尚無分數，用 status 區分。"""

    job: Job
    score: float = Field(default=0.0, ge=0, le=100, description="契合度 0~100")
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    benefits: list[str] = Field(default_factory=list)
    requires_external_apply: bool = False
    cover_letter: str | None = None
    # candidate=爬到待選 / pending=排隊分析 / done=完成 / failed=失敗
    status: str = "done"
    relevant: bool = True  # 關鍵字是否命中（廣告→False，前端預設勾選用）


class SearchRun(BaseModel):
    """一次「爬取並分析」的搜尋紀錄（歷史）。"""

    search_id: str
    user: str
    keyword: str
    target: ResumeTarget
    area: str | None = None  # 縣市代碼，逗號分隔多選；None=全台
    created_at: datetime = Field(default_factory=_utcnow)
    next_page: int = 1       # 已爬到第幾頁，爬下一頁用
    count: int = 0           # 候選總數
    crawl_status: str = "done"  # queued|crawling|done|expired|failed（搜尋頁爬取狀態）


class CrawlTask(BaseModel):
    """一筆交給本機 agent 代打 104 的任務（search 或 detail）。"""

    task_id: str
    type: str  # "search" | "detail"
    payload: dict  # search: {keyword, page, area}; detail: {code}
    status: str = "pending"  # pending|claimed|done|failed|expired
    search_id: str
    user: str
    job_id: str | None = None  # detail 任務綁定的職缺
    raw_json: dict | None = None  # agent 回填的原始 104 JSON
    error: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    claimed_at: datetime | None = None
    completed_at: datetime | None = None


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


class OfferInfo(BaseModel):
    """offer 細節，全欄位 optional；薪資為自由文字。"""

    salary: str | None = None       # 自由文字，如「月 60k＋年終 2 個月」
    level: str | None = None        # 職等 / title
    start_date: str | None = None   # 到職日
    accepted: bool | None = None    # 是否接受
    note: str | None = None         # 補充


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
    offer: OfferInfo | None = None
