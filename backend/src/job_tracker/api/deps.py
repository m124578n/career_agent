"""共用的 FastAPI 依賴：repo providers、認證、每日額度檢查。"""

from fastapi import HTTPException

from job_tracker.auth import current_user  # re-export 供 routers 使用
from job_tracker.config import get_settings
from job_tracker.db import get_db
from job_tracker.db.repositories import (
    ApplicationRepository,
    JobRepository,
    MatchRepository,
    QuotaRepository,
    SearchRepository,
    TokenUsageRepository,
)
from job_tracker.services.analyze import AnalysisRunner, AsyncioRunner

__all__ = [
    "current_user",
    "get_job_repo",
    "get_match_repo",
    "get_quota_repo",
    "get_search_repo",
    "get_application_repo",
    "get_usage_repo",
    "get_analysis_runner",
    "ensure_quota",
    "get_database",
]


def get_job_repo() -> JobRepository:
    return JobRepository(get_db())


def get_match_repo() -> MatchRepository:
    return MatchRepository(get_db())


def get_quota_repo() -> QuotaRepository:
    return QuotaRepository(get_db())


def get_search_repo() -> SearchRepository:
    return SearchRepository(get_db())


def get_application_repo() -> ApplicationRepository:
    return ApplicationRepository(get_db())


def get_usage_repo() -> TokenUsageRepository:
    return TokenUsageRepository(get_db())


def get_database():
    return get_db()


_runner = AsyncioRunner()


def get_analysis_runner() -> AnalysisRunner:
    return _runner


async def ensure_quota(user: str, quota: QuotaRepository) -> None:
    """超過每日額度則擋下（429）。"""
    limit = get_settings().daily_call_limit
    if await quota.used_today(user) >= limit:
        raise HTTPException(
            status_code=429, detail=f"今日額度已用盡（每日 {limit} 次），請明天再試"
        )
