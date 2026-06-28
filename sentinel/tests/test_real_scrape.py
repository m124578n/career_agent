from career_sentinel.scraper import real
from career_sentinel.models import Application, Message, Viewer


def test_scrape_collects_all(monkeypatch):
    monkeypatch.setattr(real, "fetch_viewers", lambda page: [Viewer(company="A", job_title="x", viewed_at="t")])
    monkeypatch.setattr(real, "fetch_applications", lambda page: [Application(job_id="1", company="A", title="x", status="已讀", applied_at="t")])
    monkeypatch.setattr(real, "fetch_messages", lambda page: [Message(thread_id="t1", company="A", last_message="hi")])
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
    snap, failed = real.scrape(object())
    assert failed == {"viewers"}
    assert snap.viewers == []
    assert len(snap.applications) == 1
