import pytest
from pydantic import ValidationError

from career_sentinel import store
from career_sentinel.models import Settings


def test_settings_defaults():
    s = Settings()
    assert s.watched_companies == [] and s.watched_keywords == [] and s.notify_time is None


def test_settings_rejects_bad_time():
    with pytest.raises(ValidationError):
        Settings(notify_time="25:99")


def test_settings_accepts_good_time_and_none():
    assert Settings(notify_time="09:30").notify_time == "09:30"
    assert Settings(notify_time=None).notify_time is None


def test_load_settings_default_when_empty(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    s = store.load_settings(conn)
    assert s == Settings()


def test_save_and_load_settings_roundtrip(tmp_path):
    conn = store.connect(tmp_path / "db.sqlite")
    store.save_settings(conn, Settings(watched_companies=["台積電"], watched_keywords=["後端"], notify_time="09:00"))
    s = store.load_settings(conn)
    assert s.watched_companies == ["台積電"]
    assert s.watched_keywords == ["後端"]
    assert s.notify_time == "09:00"
