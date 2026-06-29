from career_sentinel.models import Settings
from career_sentinel.watch import is_watched


def test_company_substring_match():
    assert is_watched("台積電股份有限公司", "後端工程師", Settings(watched_companies=["台積電"])) is True


def test_keyword_match_in_haystack():
    assert is_watched("某公司", "資深後端工程師", Settings(watched_keywords=["後端"])) is True


def test_case_insensitive():
    assert is_watched("X", "Senior BACKEND Engineer", Settings(watched_keywords=["backend"])) is True


def test_blank_entries_ignored():
    assert is_watched("台積電", "後端", Settings(watched_companies=["  "], watched_keywords=[""])) is False


def test_empty_settings_false():
    assert is_watched("台積電", "後端", Settings()) is False


def test_no_match():
    assert is_watched("台積電", "後端工程師", Settings(watched_companies=["聯發科"], watched_keywords=["前端"])) is False
