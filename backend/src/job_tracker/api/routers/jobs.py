"""職缺相關端點（M4 爬蟲 + 列表）。"""

from fastapi import APIRouter, Depends

from job_tracker.db import get_db
from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import Job
from job_tracker.services.ingest import ingest_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_repo() -> JobRepository:
    return JobRepository(get_db())


@router.get("")
async def list_jobs(repo: JobRepository = Depends(get_repo)) -> list[Job]:
    """列出已抓取的職缺。"""
    return await repo.list_jobs()


@router.post("/crawl")
async def crawl(
    keyword: str,
    page: int = 1,
    repo: JobRepository = Depends(get_repo),
) -> list[Job]:
    """以關鍵字爬取一頁 104 職缺（含詳情，請求間有節流）並存入 DB。"""
    return await ingest_jobs(keyword, repo, page=page)
