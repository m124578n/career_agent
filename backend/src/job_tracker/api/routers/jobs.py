"""職缺相關端點（M4 爬蟲 + 契合度分析 + 列表）。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from job_tracker.db import get_db
from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import Job, JobMatch, ResumeTarget
from job_tracker.services.analyze import analyze_jobs
from job_tracker.services.ingest import ingest_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_repo() -> JobRepository:
    return JobRepository(get_db())


class AnalyzeRequest(BaseModel):
    keyword: str
    target: ResumeTarget
    page: int = 1
    limit: int = 20


@router.get("")
async def list_jobs(repo: JobRepository = Depends(get_repo)) -> list[Job]:
    """列出已抓取的職缺。"""
    return await repo.list_jobs()


@router.get("/matches")
async def list_matches(repo: JobRepository = Depends(get_repo)) -> list[JobMatch]:
    """列出已分析的職缺，依契合度排序。"""
    return await repo.list_matches()


@router.post("/crawl")
async def crawl(
    keyword: str,
    page: int = 1,
    repo: JobRepository = Depends(get_repo),
) -> list[Job]:
    """以關鍵字爬取一頁 104 職缺（含詳情，請求間有節流）並存入 DB。"""
    return await ingest_jobs(keyword, repo, page=page)


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    repo: JobRepository = Depends(get_repo),
) -> list[JobMatch]:
    """爬取 + 逐筆契合度分析（對標履歷）並存入 DB，回傳排序結果。"""
    return await analyze_jobs(
        req.keyword, req.target, repo, page=req.page, limit=req.limit
    )
