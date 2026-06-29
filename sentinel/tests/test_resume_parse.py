import pytest

from career_sentinel.resume import parse_resume


def test_parse_txt():
    assert parse_resume("r.txt", "我的履歷\n後端".encode("utf-8")) == "我的履歷\n後端"


def test_parse_unsupported_raises():
    with pytest.raises(ValueError):
        parse_resume("r.png", b"x")
