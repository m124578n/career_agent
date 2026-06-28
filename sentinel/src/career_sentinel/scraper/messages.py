from __future__ import annotations

from ..models import Message

MESSAGES_URLS = [
    "https://pda.104.com.tw/api/messages/chatrooms?filter=exclusive&page=1&pageSize=20",
    "https://pda.104.com.tw/api/messages/chatrooms?filter=general&page=1&pageSize=20",
]


def has_interview(item: dict) -> bool:
    desc = (item.get("lastEvent") or {}).get("desc", "") or ""
    msg = item.get("msg", "") or ""
    return "面試" in desc or "面試" in msg


def parse_messages(data: dict) -> list[Message]:
    out: list[Message] = []
    for item in data.get("data", []):
        out.append(
            Message(
                thread_id=str(item.get("chatroomId", "")),
                company=item.get("custName", ""),
                last_message=item.get("msg", "") or "",
                has_interview_invite=has_interview(item),
                invite_date=None,
                raw=item,
            )
        )
    return out


def fetch_messages(page) -> list[Message]:
    """抓 exclusive + general 兩 filter 合併。需真瀏覽器、不單測。"""
    out: list[Message] = []
    for url in MESSAGES_URLS:
        resp = page.request.get(url)
        if not resp.ok:
            raise RuntimeError(f"messages HTTP {resp.status}")
        out.extend(parse_messages(resp.json()))
    return out
