from career_sentinel.scraper import real
from career_sentinel.models import Application, Interview, Message, Viewer


def test_scrape_collects_all(monkeypatch):
    monkeypatch.setattr(real, "fetch_viewers", lambda page: [Viewer(company="A", job_title="x", viewed_at="t")])
    monkeypatch.setattr(real, "fetch_applications", lambda page: [Application(job_id="1", company="A", title="x", status="已讀", applied_at="t")])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [Message(thread_id="t1", company="A", last_message="hi")])
    monkeypatch.setattr(real, "fetch_interviews", lambda page: [])
    snap, failed = real.scrape(object())
    assert failed == set()
    assert len(snap.viewers) == 1
    assert len(snap.applications) == 1
    assert len(snap.messages) == 1


def test_scrape_isolates_one_failure(monkeypatch):
    def boom(page):
        raise RuntimeError("down")

    monkeypatch.setattr(real, "fetch_viewers", boom)
    monkeypatch.setattr(real, "fetch_applications", lambda page: [Application(job_id="1", company="A", title="x", status="已讀", applied_at="t")])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [])
    monkeypatch.setattr(real, "fetch_interviews", lambda page: [])
    snap, failed = real.scrape(object())
    assert failed == {"viewers"}
    assert snap.viewers == []
    assert len(snap.applications) == 1


def test_scrape_collects_interviews(monkeypatch):
    monkeypatch.setattr(real, "fetch_viewers", lambda page: [])
    monkeypatch.setattr(real, "fetch_applications", lambda page: [])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [])
    monkeypatch.setattr(real, "fetch_interviews", lambda page: [Interview(company="甲", when="2026-04-07 10:00:00")])
    snap, failed = real.scrape(page=object())
    assert failed == set()
    assert len(snap.interviews) == 1
    assert snap.interviews[0].company == "甲"


def test_scrape_interviews_failure_recorded(monkeypatch):
    monkeypatch.setattr(real, "fetch_viewers", lambda page: [])
    monkeypatch.setattr(real, "fetch_applications", lambda page: [])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [])
    def boom(page): raise RuntimeError("interviews HTTP 500")
    monkeypatch.setattr(real, "fetch_interviews", boom)
    snap, failed = real.scrape(page=object())
    assert "interviews" in failed
