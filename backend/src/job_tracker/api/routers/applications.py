"""投遞紀錄端點（M5 求職信、M6 外部投遞提醒、求職進度）。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.db import get_db
from job_tracker.db.repositories import JobRepository
from job_tracker.schemas import ResumeTarget
from job_tracker.services import cover_letter

router = APIRouter(prefix="/applications", tags=["applications"])


def get_repo() -> JobRepository:
    return JobRepository(get_db())


class CoverLetterRequest(BaseModel):
    target: ResumeTarget
    job_id: str


@router.get("")
async def list_applications() -> list[dict]:
    """列出投遞紀錄（求職進度看板用）。TODO：接 db repository。"""
    return []


@router.post("/cover-letter")
async def generate_cover_letter(
    req: CoverLetterRequest,
    repo: JobRepository = Depends(get_repo),
) -> dict[str, str]:
    """對指定職缺生成求職信（M5）。"""
    job = await repo.get_job(req.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到該職缺")
    detail = await repo.get_detail(req.job_id)
    text = await cover_letter.generate(req.target, job, detail)
    return {"cover_letter": text}
