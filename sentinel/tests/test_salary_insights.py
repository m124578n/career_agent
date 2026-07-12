from career_sentinel import salary_insights
from career_sentinel.models import RecommendedJob, SalaryInsight


def _job(low, high, period):
    return RecommendedJob(code="x", url="u", salary="", salary_low=low, salary_high=high, salary_period=period)


def test_monthly_and_yearly_normalised():
    jobs = [
        _job(60000, 80000, "月薪"),      # rep 70000
        _job(1200000, 1800000, "年薪"),  # 月 100000~150000 → rep 125000
    ]
    r = salary_insights.compute_salary_insights("後端", jobs)
    assert r.sample == 2
    assert r.min_monthly == 70000 and r.max_monthly == 125000
    assert r.median_monthly == 97500  # (70000+125000)/2 內插


def test_hourly_and_negotiable_excluded_and_counted():
    jobs = [
        _job(50000, 70000, "月薪"),
        _job(200, 250, "時薪"),   # 排除
        _job(0, 0, ""),           # 面議排除
    ]
    r = salary_insights.compute_salary_insights("k", jobs)
    assert r.sample == 1 and r.hourly_excluded == 1 and r.negotiable == 1


def test_open_ended_uses_low():
    r = salary_insights.compute_salary_insights("k", [_job(60000, 0, "月薪")])
    assert r.sample == 1 and r.median_monthly == 60000


def test_empty_sample_returns_none():
    r = salary_insights.compute_salary_insights("k", [_job(0, 0, "")])
    assert r.sample == 0 and r.negotiable == 1
    assert r.median_monthly is None and r.p25_monthly is None
