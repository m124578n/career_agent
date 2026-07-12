from fastapi.testclient import TestClient

from career_sentinel import salary_insights
from career_sentinel.models import SalaryInsight
from career_sentinel.web.app import create_app


def test_salary_endpoint_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(salary_insights, "salary_insights_for_keyword",
                        lambda kw, **kw2: SalaryInsight(keyword=kw, sample=3, median_monthly=65000, negotiable=1))
    c = TestClient(create_app(db_path=str(tmp_path / "db.sqlite")))
    r = c.get("/api/salary-insights", params={"kw": "後端"})
    assert r.status_code == 200
    body = r.json()
    assert body["median_monthly"] == 65000 and body["sample"] == 3


def test_salary_endpoint_empty_kw_400(tmp_path):
    c = TestClient(create_app(db_path=str(tmp_path / "db.sqlite")))
    r = c.get("/api/salary-insights", params={"kw": "  "})
    assert r.status_code == 400
