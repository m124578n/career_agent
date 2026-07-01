import json
from pathlib import Path

from career_sentinel.scraper.interviews import parse_interviews

FIX = Path(__file__).parent / "fixtures" / "interviews.json"


def test_parse_interviews_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    ivs = parse_interviews(data)
    assert len(ivs) == 2
    iv = ivs[0]
    assert iv.company == "範例科技股份有限公司"
    assert iv.job_title == "資深後端工程師"
    assert iv.when == "2026-04-07 10:00:00"
    assert iv.location == "台北市內湖區範例路 1 號"
    assert iv.job_url == "https://www.104.com.tw/job/aa1bb"
    assert iv.status == 10
    assert iv.raw["contactName"] == "王先生"


def test_parse_interviews_skips_bad_entries():
    payload = {"data": [
        "壞字串",
        {"custName": "甲公司", "jobName": "工程師", "interviewTime": "2026-05-01 09:00:00",
         "address": "台北", "jobUrl": "u", "status": 1},
    ]}
    ivs = parse_interviews(payload)
    assert len(ivs) == 1
    assert ivs[0].company == "甲公司"


def test_parse_interviews_empty():
    assert parse_interviews({"data": []}) == []
