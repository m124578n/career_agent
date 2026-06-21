"""LLM token 用量端點。"""

from fastapi import APIRouter, Depends

from job_tracker.db import get_db
from job_tracker.db.repositories import TokenUsageRepository

router = APIRouter(prefix="/usage", tags=["usage"])


def get_usage_repo() -> TokenUsageRepository:
    return TokenUsageRepository(get_db())


@router.get("")
async def usage_summary(
    repo: TokenUsageRepository = Depends(get_usage_repo),
) -> dict:
    """回傳 token 總用量與各 model 細分。"""
    return await repo.summary()
