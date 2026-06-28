from fastapi.testclient import TestClient

from career_sentinel.web import app as webapp


def test_api_works_without_dist(tmp_path):
    # 未建置前端時，create_app 不應因缺 dist 而崩；/api 仍可用
    c = TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))
    assert c.get("/api/snapshot").status_code == 200
