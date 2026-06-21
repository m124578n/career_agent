"""履歷相關端點（M1 上傳/解析、M2 診斷）。診斷需登入且受每日額度限制。"""

from fastapi import APIRouter, Depends, File, UploadFile

from job_tracker.api.deps import current_user, ensure_quota, get_quota_repo
from job_tracker.db.repositories import QuotaRepository
from job_tracker.resume import parse_resume
from job_tracker.schemas import ResumeDiagnosis, ResumeTarget
from job_tracker.services import resume_diagnosis

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("/parse")
async def parse(
    file: UploadFile = File(...),
    user: str = Depends(current_user),
) -> dict[str, str]:
    """上傳履歷檔，回傳解析後純文字（M1）。不耗 LLM，不計額度。"""
    data = await file.read()
    text = parse_resume(file.filename or "resume", data)
    return {"text": text}


@router.post("/diagnose")
async def diagnose(
    target: ResumeTarget,
    user: str = Depends(current_user),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> ResumeDiagnosis:
    """針對目標職位分析履歷優勢／待補強（M2）。"""
    await ensure_quota(user, quota)
    result = await resume_diagnosis.diagnose(target)
    await quota.add(user, 1)
    return result
