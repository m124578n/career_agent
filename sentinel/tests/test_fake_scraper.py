from career_sentinel.scraper import fake
from career_sentinel.models import Snapshot


def test_fake_scrape_returns_populated_snapshot_and_empty_failed():
    snap, failed = fake.scrape()
    assert isinstance(snap, Snapshot)
    assert failed == set()
    assert snap.viewers and snap.applications and snap.messages
    assert any(m.has_interview_invite for m in snap.messages)
