import pytest

from career_sentinel.scraper.viewers import fetch_viewers
from career_sentinel.scraper.applications import fetch_applications
from career_sentinel.scraper.messages import fetch_messages


class _FakeResp:
    def __init__(self, ok, status, payload=None):
        self.ok = ok
        self.status = status
        self._payload = payload if payload is not None else {"data": []}

    def json(self):
        return self._payload


class _FakeRequest:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url):
        return self._resp


class _FakePage:
    def __init__(self, resp):
        self.request = _FakeRequest(resp)


def test_fetch_viewers_raises_on_not_ok():
    page = _FakePage(_FakeResp(ok=False, status=403))
    with pytest.raises(RuntimeError):
        fetch_viewers(page)


def test_fetch_applications_raises_on_not_ok():
    page = _FakePage(_FakeResp(ok=False, status=403))
    with pytest.raises(RuntimeError):
        fetch_applications(page)


def test_fetch_messages_raises_on_not_ok():
    page = _FakePage(_FakeResp(ok=False, status=403))
    with pytest.raises(RuntimeError):
        fetch_messages(page)


def test_fetch_viewers_ok_returns_parsed():
    page = _FakePage(_FakeResp(ok=True, status=200, payload={"data": []}))
    assert fetch_viewers(page) == []
