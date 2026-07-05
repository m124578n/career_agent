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
