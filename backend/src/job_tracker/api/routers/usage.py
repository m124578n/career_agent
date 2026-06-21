"""用量端點：個人 token 用量 + 每日額度；全站用量限 admin。"""

from fastapi import APIRouter, Depends, HTTPException

from job_tracker.api.deps import current_user, get_quota_repo, get_usage_repo
from job_tracker.auth import is_admin
from job_tracker.config import get_settings
from job_tracker.db.repositories import QuotaRepository, TokenUsageRepository

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def my_usage(
    user: str = Depends(current_user),
    repo: TokenUsageRepository = Depends(get_usage_repo),
) -> dict:
    """登入者自己的 token 用量。"""
    return await repo.summary(user)


@router.get("/global")
async def global_usage(
    user: str = Depends(current_user),
    repo: TokenUsageRepository = Depends(get_usage_repo),
) -> dict:
    """全站 token 用量（成本檢視）。僅 admin。"""
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="僅管理者可檢視")
    return await repo.summary()


@router.get("/quota")
async def my_quota(
    user: str = Depends(current_user),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> dict:
    """登入者今日已用次數 / 上限 / 剩餘 / 是否為 admin。"""
    limit = get_settings().daily_call_limit
    used = await quota.used_today(user)
    return {
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "is_admin": is_admin(user),
    }
