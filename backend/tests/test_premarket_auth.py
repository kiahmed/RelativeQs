"""Backend access control (RELQ_API_TOKEN) — service token or Supabase JWT, else 401."""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import auth
from app.config import settings


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_missing_token_is_401():
    with pytest.raises(HTTPException) as e:
        auth.require_api_access(None)
    assert e.value.status_code == 401


def test_service_token_accepted(monkeypatch):
    monkeypatch.setattr(settings, "RELQ_API_TOKEN", "s3cret")
    assert auth.require_api_access(_creds("s3cret"))["id"] == "service"


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setattr(settings, "RELQ_API_TOKEN", "s3cret")
    with pytest.raises(HTTPException) as e:
        auth.require_api_access(_creds("nope"))
    assert e.value.status_code == 401


def test_unset_service_token_is_not_a_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "RELQ_API_TOKEN", "")
    with pytest.raises(HTTPException):
        auth.require_api_access(_creds(""))


def test_websocket_verify_token(monkeypatch):
    monkeypatch.setattr(settings, "RELQ_API_TOKEN", "s3cret")
    assert auth.verify_access_token("s3cret") is True
    assert auth.verify_access_token("garbage") is False
    assert auth.verify_access_token("") is False


def test_routes_are_gated_except_health():
    from backend.main import app
    from fastapi.routing import APIRoute
    open_paths = set()
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            deps = {d.call for d in r.dependant.dependencies}
            if auth.require_api_access not in deps and not r.path.startswith("/api/billing"):
                open_paths.add(r.path)
    assert open_paths == {"/api/health"}
