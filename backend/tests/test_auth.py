import pytest
from fastapi import HTTPException

from job_tracker import auth


def _settings(client_id: str):
    return type("S", (), {"google_client_id": client_id})()


async def test_dev_mode_returns_default_user(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings(""))
    assert await auth.current_user(None) == "dev@local"


async def test_missing_token_raises_401(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("cid"))
    with pytest.raises(HTTPException) as e:
        await auth.current_user(None)
    assert e.value.status_code == 401


async def test_valid_token_returns_email(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("cid"))
    auth.set_verifier(lambda token, client_id: {"email": "user@example.com"})
    try:
        email = await auth.current_user("Bearer abc.def.ghi")
        assert email == "user@example.com"
    finally:
        auth.set_verifier(auth._default_verify)


async def test_invalid_token_raises_401(monkeypatch):
    monkeypatch.setattr(auth, "get_settings", lambda: _settings("cid"))

    def boom(token, client_id):
        raise ValueError("bad token")

    auth.set_verifier(boom)
    try:
        with pytest.raises(HTTPException) as e:
            await auth.current_user("Bearer bad")
        assert e.value.status_code == 401
    finally:
        auth.set_verifier(auth._default_verify)
