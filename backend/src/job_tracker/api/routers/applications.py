"""投遞紀錄端點（M5 求職信、M6 外部投遞提醒、求職進度）。求職信需登入且受額度限制。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user,
    ensure_quota,
    get_job_repo,
    get_quota_repo,
)
from job_tracker.db.repositories import JobRepository, QuotaRepository
from job_tracker.schemas import ResumeTarget
from job_tracker.services import cover_letter

router = APIRouter(prefix="/applications", tags=["applications"])


class CoverLetterRequest(BaseModel):
    target: ResumeTarget
    job_id: str


@router.post("/cover-letter")
async def generate_cover_letter(
    req: CoverLetterRequest,
    user: str = Depends(current_user),
    repo: JobRepository = Depends(get_job_repo),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> dict[str, str]:
    """對指定職缺生成求職信（M5）。"""
    job = await repo.get_job(req.job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="找不到該職缺")
    await ensure_quota(user, quota)
    detail = await repo.get_detail(req.job_id)
    text = await cover_letter.generate(req.target, job, detail)
    await quota.add(user, 1)
    return {"cover_letter": text}
