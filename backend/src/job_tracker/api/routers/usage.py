"""用量端點：全域 token 總量（成本檢視）+ 登入者每日額度。"""

from fastapi import APIRouter, Depends

from job_tracker.api.deps import current_user, get_quota_repo, get_usage_repo
from job_tracker.config import get_settings
from job_tracker.db.repositories import QuotaRepository, TokenUsageRepository

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def usage_summary(
    user: str = Depends(current_user),
    repo: TokenUsageRepository = Depends(get_usage_repo),
) -> dict:
    """全域 token 總用量與各 model 細分。"""
    return await repo.summary()


@router.get("/quota")
async def my_quota(
    user: str = Depends(current_user),
    quota: QuotaRepository = Depends(get_quota_repo),
) -> dict:
    """登入者今日已用次數 / 上限 / 剩餘。"""
    limit = get_settings().daily_call_limit
    used = await quota.used_today(user)
    return {"used": used, "limit": limit, "remaining": max(0, limit - used)}
