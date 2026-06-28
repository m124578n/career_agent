from career_sentinel import store
from career_sentinel.models import Snapshot


def test_latest_run_at_none_when_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    assert store.latest_run_at(conn) is None


def test_latest_run_at_returns_newest(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_snapshot(conn, Snapshot(), run_at="2026-06-27T10:00:00")
    store.save_snapshot(conn, Snapshot(), run_at="2026-06-28T10:00:00")
    assert store.latest_run_at(conn) == "2026-06-28T10:00:00"
