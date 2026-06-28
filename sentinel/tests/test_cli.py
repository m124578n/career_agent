from career_sentinel import cli, store
from career_sentinel.models import Snapshot
from career_sentinel.scraper import fake


def test_run_pipeline_first_run_reports_changes(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    report = cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")
    assert "台積電" in report
    assert store.latest_two_ids(conn)  # 有寫入快照


def test_run_pipeline_second_identical_run_reports_no_change(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")
    report = cli.run_pipeline(fake.scrape, conn, now="2026-06-29T10:00:00")
    assert "沒有新變化" in report


def test_main_unknown_command_returns_nonzero():
    assert cli.main(["bogus"]) != 0


def test_run_pipeline_carries_forward_failed_reader(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    cli.run_pipeline(fake.scrape, conn, now="2026-06-28T10:00:00")

    def scrape_viewers_failed():
        snap, _ = fake.scrape()
        return Snapshot(viewers=[], applications=snap.applications, messages=snap.messages), {"viewers"}

    report = cli.run_pipeline(scrape_viewers_failed, conn, now="2026-06-29T10:00:00")
    assert "未讀到" in report and "viewers" in report
    ids = store.latest_two_ids(conn)
    latest = store.load_snapshot(conn, ids[0])
    assert len(latest.viewers) == 2  # 沿用上次的兩筆、未被空清單污染
