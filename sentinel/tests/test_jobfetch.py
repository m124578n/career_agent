import json
from pathlib import Path

import pytest

from career_sentinel.jobfetch import extract_job_code, parse_job_detail

FIX = Path(__file__).parent / "fixtures" / "jd_detail.json"


def test_extract_job_code_basic():
    assert extract_job_code("https://www.104.com.tw/job/8pu2t") == "8pu2t"


def test_extract_job_code_with_query_and_slash():
    assert extract_job_code("https://www.104.com.tw/job/8pu2t/?jobsource=index") == "8pu2t"


def test_extract_job_code_non_104_raises():
    with pytest.raises(ValueError):
        extract_job_code("https://example.com/job/123")


def test_parse_job_detail_maps_fields():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    jd = parse_job_detail(data)
    assert jd.title == "全端工程師"
    assert jd.company == "範例科技有限公司"
    assert "FastAPI" in jd.description
    assert jd.salary == "月薪 50,000~70,000元"
    assert jd.work_exp == "2年以上"
    assert jd.education == "大學"
    assert jd.majors == ["資訊工程相關"]
    assert jd.specialties == ["Python", "FastAPI", "SQL"]
