from fastapi.testclient import TestClient

from career_sentinel import negotiate as negmod, store
from career_sentinel.models import NegotiationAdvice, OfferDetail
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_negotiate_endpoint_offer(tmp_path, monkeypatch):
    db = str(tmp_path / "db.sqlite")
    conn = store.connect(db)
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=1200000))
    store.set_tracked_state(conn, "of2", "offer", offer=OfferDetail(salary_year=1400000))
    from career_sentinel.models import JobPreferences
    store.save_preferences(conn, JobPreferences(expected_salary=90000))

    captured = {}
    def fake_neg(offer, company, title, other_offers, expected_salary, **kw):
        captured["others"] = other_offers
        captured["expected"] = expected_salary
        return NegotiationAdvice(summary="可談")
    monkeypatch.setattr(negmod, "negotiate_offer", fake_neg)

    c = TestClient(webapp.create_app(db_path=db))
    r = c.post("/api/negotiate", json={"code": "of1"})
    assert r.status_code == 200 and r.json()["summary"] == "可談"
    # 其他 offer（of2）當競品，期望薪資帶入
    assert any(o.get("salary_year") == 1400000 for o in captured["others"])
    assert captured["expected"] == 90000


def test_negotiate_non_offer_400(tmp_path):
    from career_sentinel.models import TrackedJob
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="m1", state="matched", match_score=70))
    r = _client(tmp_path).post("/api/negotiate", json={"code": "m1"})
    assert r.status_code == 400


def test_negotiate_missing_400(tmp_path):
    r = _client(tmp_path).post("/api/negotiate", json={"code": "nope"})
    assert r.status_code == 400
