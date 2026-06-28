import json
from pathlib import Path

from career_sentinel.scraper.viewers import parse_viewers

FIX = Path(__file__).parent / "fixtures" / "viewers.json"


def test_parse_viewers_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    viewers = parse_viewers(data)
    assert len(viewers) == 2
    v = viewers[0]
    assert v.company == "範例科技股份有限公司"
    assert v.job_title == "軟體工程師"        # jobCatTag.desc
    assert v.viewed_at == "2026-06-28 09:12"  # browseDate
    assert v.raw["custNo"] == "1a2b3c"


def test_parse_viewers_empty():
    assert parse_viewers({"data": []}) == []
