"""職缺相關端點（M4 爬蟲 + 契合度）。骨架，待實作。"""

from fastapi import APIRouter

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs() -> list[dict]:
    """列出已抓取/分析的職缺。TODO：接 db repository。"""
    return []
