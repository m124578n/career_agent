"""投遞紀錄端點（M5 求職信、M6 外部投遞提醒、求職進度）。骨架，待實作。"""

from fastapi import APIRouter

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("")
async def list_applications() -> list[dict]:
    """列出投遞紀錄（求職進度看板用）。TODO：接 db repository。"""
    return []
