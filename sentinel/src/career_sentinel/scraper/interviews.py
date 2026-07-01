from __future__ import annotations

from ..models import Interview

INTERVIEWS_URL = "https://pda.104.com.tw/api/interviews?page=1&pageSize=20"


def parse_interviews(payload: dict) -> list[Interview]:
    """把 104 面試端點 JSON 解析成 Interview；壞筆（非 dict）略過、不炸整批。"""
    out: list[Interview] = []
    for item in payload.get("data", []) or []:
        if not isinstance(item, dict):
            continue
        out.append(
            Interview(
                company=(item.get("custName") or "").strip(),
                job_title=(item.get("jobName") or "").strip(),
                when=(item.get("interviewTime") or "").strip(),
                location=(item.get("address") or "").strip(),
                status=item.get("status") if isinstance(item.get("status"), int) else None,
                job_url=(item.get("jobUrl") or "").strip(),
                raw=item,
            )
        )
    return out


def fetch_interviews(page) -> list[Interview]:
    """需已登入且已取得 pda host 的 Cloudflare clearance。需真瀏覽器、不單測。"""
    resp = page.request.get(INTERVIEWS_URL)
    if not resp.ok:
        raise RuntimeError(f"interviews HTTP {resp.status}")
    return parse_interviews(resp.json())
