from career_sentinel import cli, store
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
