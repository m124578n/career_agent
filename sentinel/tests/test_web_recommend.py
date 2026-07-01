from fastapi.testclient import TestClient

from career_sentinel.models import RecommendedJob
from career_sentinel.scraper import recommend as rec
from career_sentinel.web.app import create_app


def _client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def test_recommend_ok_marks_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "recommend_session", lambda: [
        RecommendedJob(code="aa1bb", url="https://www.104.com.tw/job/aa1bb",
                       title="後端工程師", company="關注甲公司", salary="月薪 60,000~90,000 元"),
        RecommendedJob(code="cc3dd", url="https://www.104.com.tw/job/cc3dd",
                       title="前端工程師", company="其他公司", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": ["關注甲公司"], "watched_keywords": [], "notify_time": None})
    r = client.get("/api/recommend")
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["code"] == "aa1bb" and jobs[0]["is_watched"] is True
    assert jobs[0]["salary"] == "月薪 60,000~90,000 元"
    assert jobs[1]["is_watched"] is False


def test_recommend_keyword_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "recommend_session", lambda: [
        RecommendedJob(code="aa1bb", url="u", title="資深 Python 工程師", company="甲", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": [], "watched_keywords": ["python"], "notify_time": None})
    r = client.get("/api/recommend")
    assert r.json()["jobs"][0]["is_watched"] is True


def test_recommend_not_logged_in_409(monkeypatch, tmp_path):
    monkeypatch.setattr(rec, "recommend_session", lambda: None)
    r = _client(tmp_path).get("/api/recommend")
    assert r.status_code == 409


def test_recommend_fetch_error_502(monkeypatch, tmp_path):
    def _boom():
        raise RuntimeError("recommend HTTP 403")
    monkeypatch.setattr(rec, "recommend_session", _boom)
    r = _client(tmp_path).get("/api/recommend")
    assert r.status_code == 502
