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


# The ONLY unauthenticated data routes: the container healthcheck and the landing-page
# teaser. Adding to this set is a deliberate product/security decision.
OPEN_ROUTES = {"/api/health", "/api/ai-dependency"}


def test_routes_are_gated_except_the_open_ones():
    from backend.main import app
    from fastapi.routing import APIRoute
    open_paths = set()
    for r in app.routes:
        if isinstance(r, APIRoute) and r.path.startswith("/api/"):
            deps = {d.call for d in r.dependant.dependencies}
            if auth.require_api_access not in deps and not r.path.startswith("/api/billing"):
                open_paths.add(r.path)
    assert open_paths == OPEN_ROUTES


def test_open_ai_dependency_has_no_auth_dependency_and_serves_the_teaser(monkeypatch):
    """The teaser must work for a logged-out visitor (and a stale token header can't
    matter: the route declares no auth dependency at all)."""
    import asyncio
    from backend.main import app
    from fastapi.routing import APIRoute
    from app import api

    route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/api/ai-dependency")
    assert route.dependant.dependencies == []

    async def fake_compute():
        return {"status": "ok", "dependency_now": 0.5}

    async def cold(key):
        return None

    monkeypatch.setattr(api.market, "fetch_ai_dependency", fake_compute)
    monkeypatch.setattr(api.cache, "get", cold)
    assert asyncio.run(api.ai_dependency())["dependency_now"] == 0.5

    # a gated sibling does carry the gate
    gated = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/api/prediction")
    assert auth.require_api_access in {d.call for d in gated.dependant.dependencies}
