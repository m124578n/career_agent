from __future__ import annotations

from ..models import Application

APPLICATIONS_URL = "https://pda.104.com.tw/applyRecord/ajax/list?page=1&status=all"


def derive_status(item: dict) -> str:
    """104 無單一狀態欄位，由時間戳推導。

    只有 custReplyDate（廠商對「我這筆應徵」的回覆日）才代表公司回覆了我。
    hrReplyCount / lastCustReplyTimestamp 是該職缺 HR 對「所有應徵者」的回覆統計
    （職缺回覆率），即使 >0 也不代表回覆我——104 自己也只依 custReplyDate 判定，
    故不納入推導，否則會把只被「已讀」的投遞誤判成「公司已回覆」。
    """
    if item.get("custReplyDate"):
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
    if not resp.ok:
        raise RuntimeError(f"applications HTTP {resp.status}")
    return parse_applications(resp.json())
