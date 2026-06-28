import time

from career_sentinel.web import runner


def _reset():
    runner._state.running = False
    runner._state.last_run = None
    runner._state.last_error = None
    runner._state.last_failed_readers = []


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
