import json
from pathlib import Path

from career_sentinel.scraper.recommend import parse_recommendations

FIX = Path(__file__).parent / "fixtures" / "recommend.json"


def test_parse_recommend_maps_fields_and_salary():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    jobs = parse_recommendations(data)
    assert len(jobs) == 4
    j = jobs[0]
    assert j.code == "aa1bb"
    assert j.url == "https://www.104.com.tw/job/aa1bb"
    assert j.title == "資深後端工程師"
    assert j.company == "範例雲端股份有限公司"
    assert j.salary == "月薪 60,000~90,000 元"
    assert j.is_watched is False
    assert jobs[1].salary == "月薪 55,000 元以上"   # salaryHigh=9999999
    assert jobs[2].salary == "年薪 1,500,000~2,500,000 元"  # s10=60
    assert jobs[3].salary == "面議"                 # s10=10


def test_parse_recommend_skips_bad_entries():
    payload = {"data": [
        {"jobName": "沒有 jobNo"},                       # 缺 code → 略過
        "壞字串",                                         # 非 dict → 略過
        {"jobNo": "zz9yy", "jobName": "好職缺", "custName": "甲公司",
         "salaryLow": 40000, "salaryHigh": 50000, "s10": 50},  # 無 link → 用 code 組 url
    ]}
    jobs = parse_recommendations(payload)
    assert len(jobs) == 1
    assert jobs[0].code == "zz9yy"
    assert jobs[0].url == "https://www.104.com.tw/job/zz9yy"


def test_parse_recommend_empty():
    assert parse_recommendations({"data": []}) == []
