import time

from career_sentinel.models import ChangeCounts
from career_sentinel.web import runner


def _reset():
    runner._state.running = False
    runner._state.last_run = None
    runner._state.last_error = None
    runner._state.last_failed_readers = []
    runner._state.last_change_counts = ChangeCounts()
    runner._state.phase = ""


def test_start_scrape_success_updates_state():
    _reset()
    assert runner.start_scrape(lambda: {"viewers"}) is True
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    st = runner.status()
    assert st["running"] is False
    assert st["last_run"] is not None
    assert st["last_error"] is None
    assert st["last_failed_readers"] == ["viewers"]


def test_start_scrape_rejects_concurrent():
    _reset()
    gate = {"go": False}

    def slow():
        while not gate["go"]:
            time.sleep(0.01)
        return set()

    assert runner.start_scrape(slow) is True
    assert runner.start_scrape(lambda: set()) is False  # 已在跑
    gate["go"] = True
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    assert runner.status()["running"] is False


def test_start_scrape_login_required_sets_error():
    _reset()
    def needs_login():
        raise runner.LoginRequired()
    runner.start_scrape(needs_login)
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    assert runner.status()["last_error"] == "請先 career-sentinel login"


def test_start_scrape_exception_sets_error():
    _reset()
    def boom():
        raise RuntimeError("kaboom")
    runner.start_scrape(boom)
    for _ in range(50):
        if not runner.status()["running"]:
            break
        time.sleep(0.02)
    assert "kaboom" in runner.status()["last_error"]


def test_default_scrape_saves_to_given_db(tmp_path, monkeypatch):
    from career_sentinel import store
    from career_sentinel.models import Snapshot, Viewer
    from career_sentinel.scraper import real

    snap = Snapshot(viewers=[Viewer(company="A", job_title="x", viewed_at="t")])
    monkeypatch.setattr(real, "scrape_session", lambda on_phase=None: (snap, set()))
    db = str(tmp_path / "db.sqlite")
    failed = runner.default_scrape(db)
    assert failed == set()
    assert store.latest_run_at(store.connect(db)) is not None


def test_default_scrape_records_change_counts(tmp_path, monkeypatch):
    from career_sentinel import store
    from career_sentinel.models import Snapshot, Viewer
    from career_sentinel.scraper import real
    _reset()
    db = str(tmp_path / "db.sqlite")
    # 第一次：一個 viewer（相對空前次 → 新增 1）
    snap1 = Snapshot(viewers=[Viewer(company="A", job_title="x", viewed_at="t")])
    monkeypatch.setattr(real, "scrape_session", lambda on_phase=None: (snap1, set()))
    runner.default_scrape(db)
    assert runner.status()["last_change_counts"]["new_viewers"] == 1
    # 第二次：同一 viewer（無新增 → 0）
    monkeypatch.setattr(real, "scrape_session", lambda on_phase=None: (snap1, set()))
    runner.default_scrape(db)
    assert runner.status()["last_change_counts"]["new_viewers"] == 0


def test_status_has_change_counts_key():
    _reset()
    assert "last_change_counts" in runner.status()
    assert runner.status()["last_change_counts"]["new_viewers"] == 0


def test_default_scrape_resets_counts_on_login_required(tmp_path, monkeypatch):
    import pytest
    from career_sentinel.models import ChangeCounts
    from career_sentinel.scraper import real
    _reset()
    runner._state.last_change_counts = ChangeCounts(new_viewers=3)  # 模擬上次成功的殘留
    monkeypatch.setattr(real, "scrape_session", lambda on_phase=None: None)       # 這次未登入
    with pytest.raises(runner.LoginRequired):
        runner.default_scrape(str(tmp_path / "db.sqlite"))
    assert runner.status()["last_change_counts"]["new_viewers"] == 0
