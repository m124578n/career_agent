"""履歷相關端點（M1 上傳/解析、M2 診斷）。"""

from fastapi import APIRouter, File, UploadFile

from job_tracker.resume import parse_resume
from job_tracker.schemas import ResumeDiagnosis, ResumeTarget
from job_tracker.services import resume_diagnosis

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("/parse")
async def parse(file: UploadFile = File(...)) -> dict[str, str]:
    """上傳履歷檔，回傳解析後純文字（M1）。"""
    data = await file.read()
    text = parse_resume(file.filename or "resume", data)
    return {"text": text}


@router.post("/diagnose")
async def diagnose(target: ResumeTarget) -> ResumeDiagnosis:
    """針對目標職位分析履歷優勢／待補強（M2）。"""
    return await resume_diagnosis.diagnose(target)
