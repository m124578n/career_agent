import json
from pathlib import Path

from career_sentinel.scraper.applications import derive_status, parse_applications

FIX = Path(__file__).parent / "fixtures" / "applications.json"


def test_derive_status_sent():
    assert derive_status({"custCheckDate": "", "custReplyDate": "", "hrReplyCount": 0}) == "已送出"


def test_derive_status_read():
    assert derive_status({"custCheckDate": "2026/06/28 20:00:00", "custReplyDate": "", "hrReplyCount": 0}) == "已讀"


def test_derive_status_replied_by_date():
    assert derive_status({"custCheckDate": "x", "custReplyDate": "2026/06/29", "hrReplyCount": 0}) == "公司已回覆"


def test_derive_status_replied_by_count():
    assert derive_status({"custCheckDate": "x", "custReplyDate": "", "hrReplyCount": 2}) == "公司已回覆"


def test_parse_applications_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    apps = parse_applications(data)
    assert len(apps) == 1
    a = apps[0]
    assert a.job_id == "99999999"           # str(jobNo)
    assert a.company == "範例電腦股份有限公司"
    assert a.title == "範例軟體開發工程師"
    assert a.applied_at == "2026/06/28 19:10:26"
    assert a.status == "已讀"                # custCheckDate 有值、未回覆
