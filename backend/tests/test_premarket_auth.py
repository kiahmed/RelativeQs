"""/api/premarket access control — service token or Supabase JWT, else 401."""
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import auth
from app.config import settings


def _creds(token):
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_missing_token_is_401():
    with pytest.raises(HTTPException) as e:
        auth.require_premarket_access(None)
    assert e.value.status_code == 401


def test_service_token_accepted(monkeypatch):
    monkeypatch.setattr(settings, "PREMARKET_API_TOKEN", "s3cret")
    assert auth.require_premarket_access(_creds("s3cret"))["id"] == "service"


def test_wrong_token_rejected(monkeypatch):
    monkeypatch.setattr(settings, "PREMARKET_API_TOKEN", "s3cret")
    with pytest.raises(HTTPException) as e:
        auth.require_premarket_access(_creds("nope"))
    assert e.value.status_code == 401


def test_unset_service_token_is_not_a_wildcard(monkeypatch):
    monkeypatch.setattr(settings, "PREMARKET_API_TOKEN", "")
    with pytest.raises(HTTPException):
        auth.require_premarket_access(_creds(""))
