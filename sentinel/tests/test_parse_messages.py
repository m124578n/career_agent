import json
from pathlib import Path

from career_sentinel.scraper.messages import has_interview, parse_messages

FIX = Path(__file__).parent / "fixtures" / "messages.json"


def test_has_interview_by_event_desc():
    assert has_interview({"lastEvent": {"desc": "面試邀約"}, "msg": "您好"}) is True


def test_has_interview_by_msg():
    assert has_interview({"lastEvent": {"desc": "已回覆"}, "msg": "想約您面試"}) is True


def test_has_interview_false():
    assert has_interview({"lastEvent": {"desc": "已回覆"}, "msg": "感謝您的應徵"}) is False


def test_parse_messages_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    msgs = parse_messages(data)
    assert len(msgs) == 2
    m = msgs[0]
    assert m.thread_id == "room-aaa"
    assert m.company == "範例科技股份有限公司"
    assert m.last_message == "想邀請您本週四下午來面試"
    assert m.has_interview_invite is True
    assert m.invite_date is None
    assert msgs[1].has_interview_invite is False
