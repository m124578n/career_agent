from career_sentinel import cli, store
from career_sentinel.models import Interview, Snapshot
from career_sentinel.scraper import fake


def test_run_pipeline_first_run_reports_changes(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    report, _ = cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")
    assert "台積電" in report
    assert store.latest_two_ids(conn)  # 有寫入快照


def test_run_pipeline_second_identical_run_reports_no_change(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")
    report, _ = cli.run_pipeline(fake.scrape, conn, now="2026-06-29T10:00:00")
    assert "沒有新變化" in report


def test_main_unknown_command_returns_nonzero():
    assert cli.main(["bogus"]) != 0


def test_run_pipeline_carries_forward_failed_reader(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")

    def scrape_viewers_failed():
        snap, _ = fake.scrape()
        return Snapshot(viewers=[], applications=snap.applications, messages=snap.messages), {"viewers"}

    report, _ = cli.run_pipeline(scrape_viewers_failed, conn, now="2026-06-29T10:00:00")
    assert "未讀到" in report and "viewers" in report
    ids = store.latest_two_ids(conn)
    latest = store.load_snapshot(conn, ids[0])
    assert len(latest.viewers) == 2  # 沿用上次的兩筆、未被空清單污染


def test_carry_forward_interviews(tmp_path):
    conn = store.connect(str(tmp_path / "db.sqlite"))
    prev = Snapshot(interviews=[Interview(company="舊公司", when="2026-04-01 09:00:00")])
    store.save_snapshot(conn, prev, run_at="2026-07-01T09:00:00")
    # 這次 interviews 抓取失敗 → 應沿用上次
    fresh = Snapshot(interviews=[])
    merged = cli._carry_forward(conn, fresh, {"interviews"})
    assert len(merged.interviews) == 1
    assert merged.interviews[0].company == "舊公司"
