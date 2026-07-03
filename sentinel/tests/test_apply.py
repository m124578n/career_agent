from career_sentinel.web import apply


def test_open_job_page_launches_chrome(monkeypatch):
    calls = {}
    monkeypatch.setattr(apply.browser, "find_chrome", lambda: "/usr/bin/chrome")
    monkeypatch.setattr(apply.config, "profile_dir", lambda: apply.Path("/tmp/prof"))
    monkeypatch.setattr(apply.subprocess, "Popen", lambda args, **kw: calls.setdefault("args", args))
    assert apply.open_job_page("https://www.104.com.tw/job/abc") is True
    args = calls["args"]
    assert args[0] == "/usr/bin/chrome"
    assert "--user-data-dir=/tmp/prof" in args or f"--user-data-dir={apply.Path('/tmp/prof')}" in args
    assert args[-1] == "https://www.104.com.tw/job/abc"


def test_open_job_page_no_chrome(monkeypatch):
    monkeypatch.setattr(apply.browser, "find_chrome", lambda: None)
    popen_called = {"n": 0}
    monkeypatch.setattr(apply.subprocess, "Popen", lambda *a, **k: popen_called.__setitem__("n", 1))
    assert apply.open_job_page("u") is False
    assert popen_called["n"] == 0  # 沒 Chrome 不啟動
