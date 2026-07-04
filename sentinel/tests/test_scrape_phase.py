import pytest

from career_sentinel.scraper import real
from career_sentinel.web import runner


@pytest.fixture(autouse=True)
def _reset_runner_state():
    """runner._state 是模組全域；每測後還原，避免 last_error/phase 洩漏到其他測試。"""
    yield
    runner._state.phase = ""
    runner._state.last_error = None
    runner._state.last_run = None
    runner._state.last_failed_readers = []
    runner._state.running = False


def _stub_readers(monkeypatch):
    monkeypatch.setattr(real, "fetch_viewers", lambda p: [])
    monkeypatch.setattr(real, "fetch_applications", lambda p: [])
    monkeypatch.setattr(real, "fetch_messages", lambda p: [])
    monkeypatch.setattr(real, "fetch_interviews", lambda p: [])


def test_scrape_reports_phases_in_order(monkeypatch):
    _stub_readers(monkeypatch)
    seen = []
    snap, failed = real.scrape(object(), on_phase=seen.append)
    assert seen == ["viewers", "applications", "messages", "interviews"]
    assert failed == set()


def test_scrape_on_phase_none_does_not_crash(monkeypatch):
    _stub_readers(monkeypatch)
    snap, failed = real.scrape(object())  # on_phase 預設 None
    assert failed == set()


def test_scrape_reports_all_phases_even_when_reader_fails(monkeypatch):
    _stub_readers(monkeypatch)

    def boom(p):
        raise RuntimeError("reader down")

    monkeypatch.setattr(real, "fetch_viewers", boom)
    seen = []
    snap, failed = real.scrape(object(), on_phase=seen.append)
    # phase 在每個 reader 前回報，故失敗不影響後續回報
    assert seen == ["viewers", "applications", "messages", "interviews"]
    assert "viewers" in failed


def test_set_phase_reflected_in_status():
    runner.set_phase("viewers")
    assert runner.status()["phase"] == "viewers"
    runner.set_phase("")
    assert runner.status()["phase"] == ""


def test_run_clears_phase_on_success():
    runner.set_phase("digest")
    runner._run(lambda: set())
    assert runner.status()["phase"] == ""


def test_run_clears_phase_on_exception():
    runner.set_phase("viewers")

    def boom():
        raise RuntimeError("scrape failed")

    runner._run(boom)
    assert runner.status()["phase"] == ""
    assert runner.status()["last_error"]
