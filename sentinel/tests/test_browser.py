from career_sentinel import browser


def test_is_login_url_detects_login_page():
    assert browser.is_login_url("https://www.104.com.tw/login") is True
    assert browser.is_login_url("https://account.104.com.tw/login?return=...") is True


def test_is_login_url_false_for_logged_in_page():
    assert browser.is_login_url("https://www.104.com.tw/jobs/apply/analytics") is False
