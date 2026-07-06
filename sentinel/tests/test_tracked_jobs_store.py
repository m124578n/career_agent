from career_sentinel import store
from career_sentinel.models import OfferDetail, TrackedJob


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


def test_set_offer_stores_detail(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    of = OfferDetail(salary_year=1200000, salary_month=90000, location="台北",
                     level="資深", start_date="2026-09-01", notes="含年終")
    final = store.set_tracked_state(conn, "of1", "offer", offer=of)
    assert final == "offer"
    got = store.get_tracked_job(conn, "of1")
    assert got.state == "offer"
    parsed = OfferDetail.model_validate_json(got.offer_json)
    assert parsed.salary_year == 1200000 and parsed.location == "台北" and parsed.level == "資深"


def test_set_reject_clears_offer(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=100))
    store.set_tracked_state(conn, "of1", "rejected")
    got = store.get_tracked_job(conn, "of1")
    assert got.state == "rejected" and got.offer_json == ""


def test_reset_from_offer_clears(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "of1", "offer", offer=OfferDetail(salary_year=100))
    store.set_tracked_state(conn, "of1", "interested")
    got = store.get_tracked_job(conn, "of1")
    assert got.state == "interested" and got.offer_json == ""


def test_set_state_new_code_creates(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "new1", "offer", offer=OfferDetail(salary_month=60000))
    assert store.get_tracked_job(conn, "new1").state == "offer"


def test_set_state_keeps_created_at(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="k1", state="interviewing", created_at="2026-07-01T00:00:00"))
    store.set_tracked_state(conn, "k1", "offer", offer=OfferDetail(salary_year=1))
    got = store.get_tracked_job(conn, "k1")
    assert got.created_at == "2026-07-01T00:00:00" and got.state == "offer"


def test_set_interviews_creates_and_roundtrips(tmp_path):
    from career_sentinel.models import InterviewNote
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_interviews(conn, "iv1", [InterviewNote(when="2026-07-10 一面", content="系統設計")])
    tj = store.get_tracked_job(conn, "iv1")
    assert tj is not None
    import json
    notes = [InterviewNote.model_validate(x) for x in json.loads(tj.interviews_json)]
    assert len(notes) == 1 and notes[0].when == "2026-07-10 一面" and notes[0].content == "系統設計"


def test_set_interviews_preserves_other_fields(tmp_path):
    from career_sentinel.models import InterviewNote, OfferDetail
    conn = store.connect(tmp_path / "db.sqlite")
    store.set_tracked_state(conn, "iv2", "offer", offer=OfferDetail(salary_year=999))
    store.set_interviews(conn, "iv2", [InterviewNote(when="二面", content="主管面")])
    tj = store.get_tracked_job(conn, "iv2")
    assert tj.state == "offer" and tj.offer_json != ""       # 不動 state/offer
    assert "主管面" in tj.interviews_json


def test_add_interview_note_appends(tmp_path):
    from career_sentinel.models import InterviewNote
    conn = store.connect(tmp_path / "db.sqlite")
    store.add_interview_note(conn, "iv3", InterviewNote(when="一面", content="A"))
    store.add_interview_note(conn, "iv3", InterviewNote(when="二面", content="B"))
    import json
    notes = json.loads(store.get_tracked_job(conn, "iv3").interviews_json)
    assert [n["content"] for n in notes] == ["A", "B"]


def test_add_interview_note_bad_json_survives(tmp_path):
    from career_sentinel.models import InterviewNote, TrackedJob
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="iv4", interviews_json="{not json"))
    store.add_interview_note(conn, "iv4", InterviewNote(when="x", content="y"))
    import json
    notes = json.loads(store.get_tracked_job(conn, "iv4").interviews_json)
    assert len(notes) == 1 and notes[0]["content"] == "y"


def test_migrate_adds_interviews_json(tmp_path):
    import sqlite3
    p = tmp_path / "db.sqlite"
    raw = sqlite3.connect(str(p))
    raw.execute(
        "CREATE TABLE tracked_jobs (code TEXT PRIMARY KEY, company TEXT NOT NULL DEFAULT '', "
        "title TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', salary TEXT NOT NULL DEFAULT '', "
        "state TEXT NOT NULL DEFAULT 'interested', match_score INTEGER, created_at TEXT NOT NULL DEFAULT '', "
        "updated_at TEXT NOT NULL DEFAULT '', match_json TEXT NOT NULL DEFAULT '', "
        "tailor_json TEXT NOT NULL DEFAULT '', offer_json TEXT NOT NULL DEFAULT '')"
    )
    raw.execute("INSERT INTO tracked_jobs (code, state) VALUES ('old1', 'matched')")
    raw.commit(); raw.close()
    conn = store.connect(p)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tracked_jobs)")}
    assert "interviews_json" in cols
    got = store.get_tracked_job(conn, "old1")
    assert got is not None and got.state == "matched" and got.interviews_json == ""
