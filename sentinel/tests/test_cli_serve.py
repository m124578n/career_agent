from career_sentinel import cli


def test_serve_dispatches(monkeypatch):
    called = {"serve": False}
    monkeypatch.setattr(cli, "_cmd_serve", lambda: called.__setitem__("serve", True) or 0)
    rc = cli.main(["serve"])
    assert rc == 0
    assert called["serve"] is True
