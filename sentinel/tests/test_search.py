import json
from pathlib import Path

from career_sentinel.scraper.search import parse_search

FIX = Path(__file__).parent / "fixtures" / "search.json"


def test_parse_search_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    jobs = parse_search(data)
    assert len(jobs) == 2
    j = jobs[0]
    assert j.code == "14221079"                              # jobNo
    assert j.url == "https://www.104.com.tw/job/8gt1z"       # link.job（短 code）
    assert j.title == "資料軟體工程師"
    assert j.company == "範例數據股份有限公司"
    assert j.salary == "月薪 43,000~47,000 元"
    assert j.is_watched is False
    assert jobs[1].salary == "月薪 60,000 元以上"             # salaryHigh=9999999


def test_parse_search_empty():
    assert parse_search({"data": []}) == []
