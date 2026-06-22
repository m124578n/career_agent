"""求職追蹤清單端點（加入／看板列表／改狀態／移除）。需登入，不耗 LLM 額度。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from job_tracker.api.deps import (
    current_user,
    get_application_repo,
    get_match_repo,
    get_search_repo,
)
from job_tracker.db.repositories import (
    ApplicationRepository,
    MatchRepository,
    SearchRepository,
)
from job_tracker.schemas import Application, ApplicationStatus

router = APIRouter(prefix="/applications", tags=["applications"])


class AddApplicationRequest(BaseModel):
    search_id: str
    job_id: str


class UpdateStatusRequest(BaseModel):
    status: ApplicationStatus


@router.post("")
async def add_application(
    req: AddApplicationRequest,
    user: str = Depends(current_user),
    search_repo: SearchRepository = Depends(get_search_repo),
    match_repo: MatchRepository = Depends(get_match_repo),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> Application:
    """把某搜尋裡的職缺加入追蹤清單（job 與求職信快照）。"""
    run = await search_repo.get(req.search_id)
    if run is None or run.user != user:
        raise HTTPException(status_code=404, detail="找不到該搜尋紀錄")
    match = await match_repo.get_match(req.search_id, req.job_id)
    if match is None:
        raise HTTPException(status_code=404, detail="找不到該職缺分析")
    app_obj = Application(
        user=user,
        job_id=req.job_id,
        job=match.job,
        source_search_id=req.search_id,
        cover_letter=match.cover_letter,
    )
    return await app_repo.add(app_obj)


@router.get("")
async def list_applications(
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> list[Application]:
    return await app_repo.list(user)


@router.patch("/{job_id}")
async def update_status(
    job_id: str,
    req: UpdateStatusRequest,
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> Application:
    updated = await app_repo.set_status(user, job_id, req.status)
    if updated is None:
        raise HTTPException(status_code=404, detail="找不到該追蹤項目")
    return updated


@router.delete("/{job_id}")
async def remove_application(
    job_id: str,
    user: str = Depends(current_user),
    app_repo: ApplicationRepository = Depends(get_application_repo),
) -> dict:
    await app_repo.remove(user, job_id)
    return {"ok": True}
