from urllib.parse import parse_qs, urlparse

from career_sentinel.calendar_link import build_gcal_link
from career_sentinel.models import Interview


def test_gcal_link_with_time():
    iv = Interview(company="甲公司", job_title="後端工程師", when="2026-04-07 10:00:00",
                   location="台北市內湖區", job_url="https://www.104.com.tw/job/aa1bb")
    url = build_gcal_link(iv)
    q = parse_qs(urlparse(url).query)
    assert q["action"] == ["TEMPLATE"]
    assert q["text"] == ["面試：甲公司"]
    assert q["dates"] == ["20260407T100000/20260407T110000"]  # 起 / 起+1h
    assert q["location"] == ["台北市內湖區"]
    assert "後端工程師" in q["details"][0]
    assert "https://www.104.com.tw/job/aa1bb" in q["details"][0]


def test_gcal_link_without_time_omits_dates():
    iv = Interview(company="乙公司", job_title="PM", when="", location="新竹")
    url = build_gcal_link(iv)
    q = parse_qs(urlparse(url).query)
    assert "dates" not in q
    assert q["text"] == ["面試：乙公司"]


def test_gcal_link_unparseable_time_omits_dates():
    iv = Interview(company="丙", job_title="x", when="待通知")
    q = parse_qs(urlparse(build_gcal_link(iv)).query)
    assert "dates" not in q
