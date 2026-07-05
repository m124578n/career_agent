from career_sentinel import pipeline, store
from career_sentinel.models import (
    Application, Interview, Snapshot, TrackedJob,
)


def _conn_with(tmp_path, snap: Snapshot):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, snap, run_at="2026-07-05T10:00:00")
    return conn


# ---- effective_state 純函式 ----

def test_effective_state_signal_only():
    assert pipeline.effective_state(None, 4) == "applied"
    assert pipeline.effective_state(None, 5) == "interviewing"


def test_effective_state_takes_furthest():
    # 手動 tailored(3) 但 104 已 applied(4) → 取較前面的 applied
    assert pipeline.effective_state("tailored", 4) == "applied"
    # 手動 interested(1) 但 104 interviewing(5) → interviewing
    assert pipeline.effective_state("interested", 5) == "interviewing"


def test_effective_state_manual_only():
    assert pipeline.effective_state("matched", 0) == "matched"


def test_effective_state_terminal_overrides():
    # 手動 offer 覆蓋 104 的 interviewing
    assert pipeline.effective_state("offer", 5) == "offer"
    assert pipeline.effective_state("rejected", 4) == "rejected"


# ---- build_pipeline 整合 ----

def test_build_empty_db_returns_list(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")  # 無 snapshot
    assert pipeline.build_pipeline(conn) == []


def test_build_applications_become_applied(tmp_path):
    snap = Snapshot(applications=[
        Application(job_id="a1", company="甲", title="後端", status="已讀", applied_at="2026-07-01"),
    ])
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "a1"
    assert jobs[0].state == "applied"
    assert jobs[0].status == "已讀"


def test_build_interview_with_code(tmp_path):
    snap = Snapshot(interviews=[
        Interview(company="乙", job_title="前端", when="2026-07-10 14:00:00",
                  location="台北", job_url="https://www.104.com.tw/job/bb2cc"),
    ])
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "bb2cc"
    assert jobs[0].state == "interviewing"
    assert jobs[0].gcal_link  # 有帶 gcal 連結
    assert jobs[0].when == "2026-07-10 14:00:00"


def test_build_interview_without_code_uses_fallback_key(tmp_path):
    snap = Snapshot(interviews=[
        Interview(company="丙", job_title="PM", when="2026-07-11 09:00:00", location="遠端", job_url=""),
    ])
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == ""
    assert jobs[0].key == "丙|PM|2026-07-11 09:00:00"
    assert jobs[0].state == "interviewing"


def test_build_merges_same_code_application_and_interview(tmp_path):
    snap = Snapshot(
        applications=[Application(job_id="dd3ee", company="丁", title="資料", status="已讀", applied_at="2026-07-01")],
        interviews=[Interview(company="丁", job_title="資料", when="2026-07-12 10:00:00",
                              location="台中", job_url="https://www.104.com.tw/job/dd3ee")],
    )
    conn = _conn_with(tmp_path, snap)
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1  # 同 code 併成一筆
    assert jobs[0].state == "interviewing"  # 取較前面
    assert jobs[0].status == "已讀"          # application 欄位仍保留
    assert jobs[0].when == "2026-07-12 10:00:00"


def test_build_tracked_terminal_overrides_signal(tmp_path):
    snap = Snapshot(interviews=[
        Interview(company="戊", job_title="後端", when="2026-07-13 10:00:00",
                  location="台北", job_url="https://www.104.com.tw/job/ff4gg"),
    ])
    conn = _conn_with(tmp_path, snap)
    store.upsert_tracked_job(conn, TrackedJob(code="ff4gg", state="offer", salary="年薪 120 萬"))
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].state == "offer"        # 終端手動覆蓋 interviewing
    assert jobs[0].salary == "年薪 120 萬"  # tracked 欄位帶入


def test_build_tracked_only_job_appears(tmp_path):
    # tracked_jobs 有、104 完全沒有的職缺也要進清單
    conn = store.connect(tmp_path / "db.sqlite")
    store.upsert_tracked_job(conn, TrackedJob(code="gg5hh", company="己", title="設計", state="matched", match_score=75))
    jobs = pipeline.build_pipeline(conn)
    assert len(jobs) == 1
    assert jobs[0].code == "gg5hh"
    assert jobs[0].state == "matched"
    assert jobs[0].match_score == 75


def test_build_swallows_errors(tmp_path, monkeypatch):
    conn = store.connect(tmp_path / "db.sqlite")
    monkeypatch.setattr(store, "load_tracked_jobs", lambda c: (_ for _ in ()).throw(RuntimeError("boom")))
    assert pipeline.build_pipeline(conn) == []  # best-effort：吞例外回空清單
