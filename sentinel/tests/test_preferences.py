import json
import sqlite3
from fastapi.testclient import TestClient
from career_sentinel import store
from career_sentinel.models import JobPreferences, ResumeState
from career_sentinel.web import app as webapp


def _client(tmp_path):
    return TestClient(webapp.create_app(db_path=str(tmp_path / "db.sqlite")))


def test_preferences_new_fields_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_preferences(conn, JobPreferences(
        target_title="後端工程師", expected_salary=900000,
        locations=["台北"], conditions=["可遠端"], avoid=["博弈"]))
    p = store.load_preferences(conn)
    assert p.target_title == "後端工程師" and p.expected_salary == 900000
    assert p.locations == ["台北"] and p.avoid == ["博弈"]


def test_migrate_copies_from_resume(tmp_path):
    # 舊資料：resume 有 target_title/expected_salary、prefs 尚未有
    p = tmp_path / "db.sqlite"
    store.connect(p).close()  # 建表
    c = sqlite3.connect(str(p))
    c.execute("INSERT OR REPLACE INTO resume (id, data) VALUES (1, ?)",
              (json.dumps({"resume_text": "履歷", "target_title": "後端", "expected_salary": 60000}),))
    c.commit(); c.close()
    conn = store.connect(p)  # connect 應觸發遷移
    pref = store.load_preferences(conn)
    assert pref.target_title == "後端" and pref.expected_salary == 60000


def test_migrate_idempotent_no_overwrite(tmp_path):
    p = tmp_path / "db.sqlite"
    conn = store.connect(p)
    store.save_preferences(conn, JobPreferences(target_title="既有職稱"))
    conn.close()
    c = sqlite3.connect(str(p))
    c.execute("INSERT OR REPLACE INTO resume (id, data) VALUES (1, ?)",
              (json.dumps({"resume_text": "x", "target_title": "舊職稱"}),))
    c.commit(); c.close()
    conn = store.connect(p)  # 再次 connect
    assert store.load_preferences(conn).target_title == "既有職稱"  # 不被覆寫


def test_migrate_no_resume_noop(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_preferences(conn).target_title == ""


def test_get_put_preferences(tmp_path):
    c = _client(tmp_path)
    body = {"target_title": "資料工程師", "expected_salary": 80000,
            "locations": ["新竹"], "conditions": ["彈性工時"], "avoid": ["外派"]}
    r = c.put("/api/preferences", json=body)
    assert r.status_code == 200
    got = c.get("/api/preferences").json()
    assert got["target_title"] == "資料工程師" and got["expected_salary"] == 80000
    assert got["locations"] == ["新竹"] and got["avoid"] == ["外派"]


def test_get_preferences_default(tmp_path):
    got = _client(tmp_path).get("/api/preferences").json()
    assert got["target_title"] == "" and got["expected_salary"] is None and got["locations"] == []
