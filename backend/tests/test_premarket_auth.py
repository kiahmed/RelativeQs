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


def _route(path):
    from backend.main import app
    from fastapi.routing import APIRoute
    return next(r for r in app.routes if isinstance(r, APIRoute) and r.path == path)


def test_open_ai_dependency_declares_no_auth_and_prediction_still_does():
    """No auth dependency on the teaser (so a stale Authorization header can't turn
    it into a 401), while a sibling data route keeps the gate."""
    assert _route("/api/ai-dependency").dependant.dependencies == []
    assert auth.require_api_access in {d.call for d in _route("/api/prediction").dependant.dependencies}


@pytest.fixture
def anon_ai(monkeypatch):
    """The public route with every upstream path instrumented: any download or
    on-demand compute is counted, and the prediction cache starts cold."""
    from app import api
    calls = {"download": 0, "compute": 0}

    def count_download(*a, **k):
        calls["download"] += 1
        raise AssertionError("anonymous request must never download")

    async def count_compute(*a, **k):
        calls["compute"] += 1
        raise AssertionError("anonymous request must never compute")

    async def cold(key):
        return None

    monkeypatch.setattr(api.market, "_download_intraday_history", count_download)
    monkeypatch.setattr(api.market, "fetch_ai_dependency", count_compute)
    monkeypatch.setattr(api.cache, "get", cold)
    monkeypatch.setattr(api.market, "_ai_dep_cache", None)
    return api, calls


def test_cold_cache_serves_a_placeholder_and_never_fetches_upstream(anon_ai):
    import asyncio
    from fastapi import Response
    api, calls = anon_ai

    async def hammer():
        resps = [Response() for _ in range(20)]
        out = await asyncio.gather(*[api.ai_dependency(r) for r in resps])
        return out, resps

    out, resps = asyncio.run(hammer())          # 20 concurrent cold, anonymous calls
    assert calls == {"download": 0, "compute": 0}
    assert all(o["status"] == "warming_up" for o in out)
    assert all(r.headers["cache-control"] == "no-store" for r in resps)  # placeholder is not cached


def test_serves_the_poll_loops_result_when_warm(anon_ai, monkeypatch):
    import asyncio
    from fastapi import Response
    api, calls = anon_ai
    good = {"status": "ok", "dependency_now": 0.55}

    # from the in-process daily cache
    monkeypatch.setattr(api.market, "_ai_dep_cache", good)
    r = Response()
    assert asyncio.run(api.ai_dependency(r)) == good
    assert r.headers["cache-control"] == "public, max-age=300"

    # from the cached prediction (preferred)
    async def warm(key):
        return {"ai_dependency": {"status": "ok", "dependency_now": 0.6}}
    monkeypatch.setattr(api.cache, "get", warm)
    assert asyncio.run(api.ai_dependency(Response()))["dependency_now"] == 0.6
    assert calls == {"download": 0, "compute": 0}


def test_api_docs_are_off_by_default():
    from backend.main import app
    paths = {getattr(r, "path", None) for r in app.routes}
    assert not ({"/docs", "/redoc", "/openapi.json"} & paths)
    assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None
