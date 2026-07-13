"""意見回饋端點：登入者送出；admin 私密收件匣（列表/已讀/刪除）。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import current_user, get_feedback_repo
from job_tracker.auth import is_admin
from job_tracker.db.repositories import FeedbackRepository
from job_tracker.schemas import Feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])

_CATEGORIES = {"建議", "問題回報", "其他"}
_MAX_LEN = 2000


class SubmitFeedbackRequest(BaseModel):
    message: str
    category: str = "其他"


class ReadRequest(BaseModel):
    read: bool


@router.post("")
async def submit_feedback(
    req: SubmitFeedbackRequest,
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> dict:
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="請輸入內容")
    if len(msg) > _MAX_LEN:
        raise HTTPException(status_code=400, detail="內容過長（上限 2000 字）")
    category = req.category if req.category in _CATEGORIES else "其他"
    await repo.create(user, msg, category)
    return {"ok": True}


@router.get("")
async def list_feedback(
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> list[Feedback]:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可檢視")
    return await repo.list()


@router.post("/{fid}/read")
async def set_feedback_read(
    fid: str,
    req: ReadRequest,
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> dict:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可操作")
    await repo.mark_read(fid, req.read)
    return {"ok": True}


@router.delete("/{fid}")
async def delete_feedback(
    fid: str,
    user: str = Depends(current_user),
    repo: FeedbackRepository = Depends(get_feedback_repo),
) -> dict:
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可操作")
    await repo.delete(fid)
    return {"ok": True}
