from career_sentinel.scraper.recommend import parse_recommendations


def _payload(jobs):
    return {"data": jobs}


def _job(no, low, high, s10):
    return {"jobNo": no, "jobName": "後端", "custName": "甲",
            "salaryLow": low, "salaryHigh": high, "s10": s10,
            "link": {"job": f"https://www.104.com.tw/job/{no}"}}


def test_parse_structured_salary_monthly_range():
    r = parse_recommendations(_payload([_job("a", 60000, 90000, 50)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (60000, 90000, "月薪")
    assert r.salary == "月薪 60,000~90,000 元"


def test_parse_structured_salary_yearly():
    r = parse_recommendations(_payload([_job("b", 1200000, 1800000, 60)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (1200000, 1800000, "年薪")


def test_parse_structured_salary_open_ended():
    r = parse_recommendations(_payload([_job("c", 60000, 9999999, 50)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (60000, 0, "月薪")
    assert r.salary == "月薪 60,000 元以上"


def test_parse_structured_salary_negotiable():
    r = parse_recommendations(_payload([_job("d", 0, 0, 10)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (0, 0, "")
    assert r.salary == "面議"


def test_parse_non_numeric_salary_does_not_raise():
    r = parse_recommendations(_payload([_job("e", "N/A", None, 50)]))[0]
    assert (r.salary_low, r.salary_high, r.salary_period) == (0, 0, "")
    assert r.salary == "面議"
