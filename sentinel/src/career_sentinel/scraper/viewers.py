from __future__ import annotations

from ..models import Viewer

VIEWERS_URL = "https://pda.104.com.tw/api/peruse-record/companies?page=1"


def parse_viewers(data: dict) -> list[Viewer]:
    out: list[Viewer] = []
    for item in data.get("data", []):
        out.append(
            Viewer(
                company=item.get("custName", ""),
                job_title=(item.get("jobCatTag") or {}).get("desc", ""),
                viewed_at=item.get("browseDate", ""),
                raw=item,
            )
        )
    return out


def fetch_viewers(page) -> list[Viewer]:
    """需已登入且已取得 pda host 的 Cloudflare clearance。需真瀏覽器、不單測。"""
    resp = page.request.get(VIEWERS_URL)
    if not resp.ok:
        raise RuntimeError(f"viewers HTTP {resp.status}")
    return parse_viewers(resp.json())
