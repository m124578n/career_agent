from career_sentinel import store
from career_sentinel.models import TrackedJob


def test_upsert_and_load_tracked_jobs(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.load_tracked_jobs(conn) == []
    store.upsert_tracked_job(conn, TrackedJob(
        code="abc12", company="台積電", title="後端工程師", url="https://www.104.com.tw/job/abc12",
        salary="月薪 6 萬", state="tailored", match_score=82,
        created_at="2026-07-05T10:00:00", updated_at="2026-07-05T10:00:00",
    ))
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "abc12"
    assert jobs[0].state == "tailored"
    assert jobs[0].match_score == 82


def test_upsert_overwrites_same_code(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="matched", match_score=70))
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="tailored", match_score=88))
    jobs = store.load_tracked_jobs(conn)
    assert len(jobs) == 1  # 同 code 覆寫、不重複
    assert jobs[0].state == "tailored"
    assert jobs[0].match_score == 88


def test_get_tracked_job_by_code(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.get_tracked_job(conn, "nope") is None
    store.upsert_tracked_job(conn, TrackedJob(code="abc12", state="interested"))
    got = store.get_tracked_job(conn, "abc12")
    assert got is not None and got.state == "interested"


def test_match_score_none_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="x1"))  # match_score 預設 None
    assert store.get_tracked_job(conn, "x1").match_score is None


def test_old_db_gains_tracked_jobs_table(tmp_path):
    # 既有 DB 重連即長出新表（加法式遷移）
    p = tmp_path / "db.sqlite"
    store.connect(p).close()
    conn = store.connect(p)
    assert store.load_tracked_jobs(conn) == []


def test_offer_json_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(
        code="of1", state="offer", offer_json='{"salary_year": 1200000, "location": "台北"}'))
    got = store.get_tracked_job(conn, "of1")
    assert got is not None
    assert got.offer_json == '{"salary_year": 1200000, "location": "台北"}'


def test_offer_json_defaults_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="of2", state="matched"))
    assert store.get_tracked_job(conn, "of2").offer_json == ""


def test_migrate_adds_offer_json_to_existing_table(tmp_path):
    # 模擬「offer_json 進 schema 之前」的舊 DB：完整欄位但缺 offer_json
    import sqlite3
    p = tmp_path / "db.sqlite"
    raw = sqlite3.connect(str(p))
    raw.execute(
        "CREATE TABLE tracked_jobs ("
        "code TEXT PRIMARY KEY, company TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', "
        "url TEXT NOT NULL DEFAULT '', salary TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'interested', "
        "match_score INTEGER, created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '', "
        "match_json TEXT NOT NULL DEFAULT '', tailor_json TEXT NOT NULL DEFAULT '')"
    )
    raw.execute("INSERT INTO tracked_jobs (code, state) VALUES ('old1', 'matched')")
    raw.commit()
    raw.close()
    conn = store.connect(p)  # 應冪等補上 offer_json 欄，不丟資料
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tracked_jobs)")}
    assert "offer_json" in cols
    got = store.get_tracked_job(conn, "old1")
    assert got is not None and got.state == "matched" and got.offer_json == ""
