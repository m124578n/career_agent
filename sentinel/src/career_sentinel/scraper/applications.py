from __future__ import annotations

from ..models import Application

APPLICATIONS_URL = "https://pda.104.com.tw/applyRecord/ajax/list?page=1&status=all"


def derive_status(item: dict) -> str:
    """104 無單一狀態欄位，由時間戳推導。"""
    if item.get("custReplyDate") or (item.get("hrReplyCount") or 0) > 0:
        return "公司已回覆"
    if item.get("custCheckDate"):
        return "已讀"
    return "已送出"


def parse_applications(data: dict) -> list[Application]:
    out: list[Application] = []
    for item in data.get("data", []):
        out.append(
            Application(
                job_id=str(item.get("jobNo", "")),
                company=item.get("custName", ""),
                title=item.get("jobName", ""),
                status=derive_status(item),
                applied_at=item.get("applyDate", ""),
                raw=item,
            )
        )
    return out


def fetch_applications(page) -> list[Application]:
    """需已登入且已取得 pda host clearance。需真瀏覽器、不單測。"""
    resp = page.request.get(APPLICATIONS_URL)
    return parse_applications(resp.json())
