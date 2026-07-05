import json
from career_sentinel import store
from career_sentinel.models import TrackedJob


def test_columns_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="a1", match_json='{"score":80}', tailor_json='{"x":1}'))
    j = store.get_tracked_job(conn, "a1")
    assert j.match_json == '{"score":80}' and j.tailor_json == '{"x":1}'


def test_old_db_gains_columns(tmp_path):
    # 模擬缺兩欄的舊 schema：先手動建一張沒有 match_json/tailor_json 的 tracked_jobs
    import sqlite3
    p = tmp_path / "db.sqlite"
    c = sqlite3.connect(str(p))
    c.execute("CREATE TABLE tracked_jobs (code TEXT PRIMARY KEY, company TEXT, title TEXT, url TEXT, "
              "salary TEXT, state TEXT, match_score INTEGER, created_at TEXT, updated_at TEXT)")
    c.execute("INSERT INTO tracked_jobs (code, state) VALUES ('old1','interested')")
    c.commit(); c.close()
    conn = store.connect(p)  # connect 應冪等 ALTER 補欄
    j = store.get_tracked_job(conn, "old1")
    assert j is not None and j.match_json == "" and j.tailor_json == ""


def test_merge_new_job_defaults_interested(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    final = store.merge_tracked_job(conn, "a1", company="甲", title="後端")
    assert final == "interested"
    assert store.get_tracked_job(conn, "a1").company == "甲"


def test_merge_matched_stores_match_json(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    final = store.merge_tracked_job(conn, "a1", state="matched", match_score=88,
                                    match_json={"score": 88, "reasons": ["r1"]})
    assert final == "matched"
    j = store.get_tracked_job(conn, "a1")
    assert j.match_score == 88
    assert json.loads(j.match_json)["reasons"] == ["r1"]


def test_merge_tailored_stores_tailor_json(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    final = store.merge_tracked_job(conn, "a1", state="tailored",
                                    tailor_json={"cover_letter": "您好"})
    assert final == "tailored"
    assert json.loads(store.get_tracked_job(conn, "a1").tailor_json)["cover_letter"] == "您好"


def test_merge_keeps_created_at_and_furthest(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="a1", state="matched", match_score=80,
                                              created_at="2026-07-01T00:00:00"))
    store.merge_tracked_job(conn, "a1", state="interested")  # 較後面，應維持 matched
    j = store.get_tracked_job(conn, "a1")
    assert j.state == "matched" and j.created_at == "2026-07-01T00:00:00"


def test_merge_does_not_downgrade_terminal(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="a1", state="offer", created_at="2026-07-01T00:00:00"))
    store.merge_tracked_job(conn, "a1", state="tailored", tailor_json={"cover_letter": "x"})
    j = store.get_tracked_job(conn, "a1")
    assert j.state == "offer"  # 不降級
    assert json.loads(j.tailor_json)["cover_letter"] == "x"  # 但快取仍寫入


def test_merge_keeps_old_json_when_not_provided(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.merge_tracked_job(conn, "a1", state="matched", match_score=80, match_json={"score": 80})
    store.merge_tracked_job(conn, "a1", state="tailored", tailor_json={"cover_letter": "y"})
    j = store.get_tracked_job(conn, "a1")
    assert json.loads(j.match_json)["score"] == 80  # match_json 未帶時保留
    assert json.loads(j.tailor_json)["cover_letter"] == "y"
