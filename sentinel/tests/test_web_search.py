from fastapi.testclient import TestClient

from career_sentinel.models import RecommendedJob
from career_sentinel.scraper import search as srch
from career_sentinel.web.app import create_app


def _client(tmp_path):
    return TestClient(create_app(db_path=str(tmp_path / "t.db")))


def test_search_ok_marks_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(srch, "fetch_search", lambda kw, page=1: [
        RecommendedJob(code="1", url="https://www.104.com.tw/job/aa", title="Python 工程師", company="關注甲公司", salary="月薪 60,000~90,000 元"),
        RecommendedJob(code="2", url="https://www.104.com.tw/job/bb", title="前端工程師", company="其他公司", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": ["關注甲公司"], "watched_keywords": [], "notify_time": None})
    r = client.get("/api/search", params={"kw": "Python"})
    assert r.status_code == 200
    jobs = r.json()["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["is_watched"] is True
    assert jobs[1]["is_watched"] is False


def test_search_keyword_watched(monkeypatch, tmp_path):
    monkeypatch.setattr(srch, "fetch_search", lambda kw, page=1: [
        RecommendedJob(code="1", url="u", title="資深 Python 工程師", company="甲", salary="面議"),
    ])
    client = _client(tmp_path)
    client.put("/api/settings", json={"watched_companies": [], "watched_keywords": ["python"], "notify_time": None})
    r = client.get("/api/search", params={"kw": "工程師"})
    assert r.json()["jobs"][0]["is_watched"] is True


def test_search_passes_page_and_reports_has_more(monkeypatch, tmp_path):
    captured = {}
    def fake(kw, page=1):
        captured["kw"], captured["page"] = kw, page
        return [RecommendedJob(code=str(i), url="u", title="t", company="c", salary="面議")
                for i in range(20)]  # 滿頁
    monkeypatch.setattr(srch, "fetch_search", fake)
    r = _client(tmp_path).get("/api/search", params={"kw": "Python", "page": 2})
    body = r.json()
    assert captured["page"] == 2
    assert body["page"] == 2 and body["has_more"] is True and len(body["jobs"]) == 20


def test_search_empty_keyword_400(tmp_path):
    r = _client(tmp_path).get("/api/search", params={"kw": "  "})
    assert r.status_code == 400


def test_search_missing_keyword_400(tmp_path):
    r = _client(tmp_path).get("/api/search")
    assert r.status_code == 400


def test_search_fetch_error_502(monkeypatch, tmp_path):
    def _boom(kw, page=1):
        raise RuntimeError("search HTTP 500")
    monkeypatch.setattr(srch, "fetch_search", _boom)
    r = _client(tmp_path).get("/api/search", params={"kw": "Python"})
    assert r.status_code == 502
