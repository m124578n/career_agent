from datetime import datetime

from career_sentinel.web import scheduler


def _at(hhmm: str) -> datetime:
    h, m = hhmm.split(":")
    return datetime(2026, 7, 1, int(h), int(m))


def test_should_prompt_at_time_not_yet_prompted():
    assert scheduler.should_prompt(_at("12:00"), "12:00", None) is True

def test_should_prompt_after_time():
    assert scheduler.should_prompt(_at("13:30"), "12:00", None) is True

def test_should_prompt_before_time():
    assert scheduler.should_prompt(_at("11:00"), "12:00", None) is False

def test_should_prompt_already_prompted_today():
    assert scheduler.should_prompt(_at("12:00"), "12:00", "2026-07-01") is False

def test_should_prompt_prompted_yesterday_reprompts():
    assert scheduler.should_prompt(_at("12:00"), "12:00", "2026-06-30") is True

def test_should_prompt_no_notify_time():
    assert scheduler.should_prompt(_at("12:00"), None, None) is False

def test_initial_prompted_date_past_marks_today():
    assert scheduler.initial_prompted_date(_at("13:00"), "12:00") == "2026-07-01"

def test_initial_prompted_date_before_returns_none():
    assert scheduler.initial_prompted_date(_at("11:00"), "12:00") is None

def test_initial_prompted_date_no_time_returns_none():
    assert scheduler.initial_prompted_date(_at("13:00"), None) is None


def test_ack_clears_due():
    scheduler._reset_for_test()
    scheduler._state.due = True
    scheduler.ack()
    assert scheduler.state()["due"] is False

def test_state_shape():
    scheduler._reset_for_test()
    s = scheduler.state()
    assert set(s.keys()) == {"due", "notify_time", "last_prompted_date"}
    assert s["due"] is False
