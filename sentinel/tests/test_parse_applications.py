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


def test_hr_reply_count_is_job_level_not_personal_reply():
    # hrReplyCount / lastCustReplyTimestamp 是「該職缺 HR 對所有應徵者的回覆」統計，
    # 不代表回覆了「我」。104 判定回覆看的是 custReplyDate。custReplyDate 空 → 仍是已讀。
    assert (
        derive_status(
            {
                "custCheckDate": "2026/07/09 20:08:14",
                "custReplyDate": "",
                "hrReplyCount": 5,
                "lastCustReplyTimestamp": 1783992272,
            }
        )
        == "已讀"
    )


def test_derive_status_replied_needs_cust_reply_date():
    assert (
        derive_status({"custCheckDate": "x", "custReplyDate": "2026/06/29", "hrReplyCount": 0})
        == "公司已回覆"
    )


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
