"""
Authentication — verification of Supabase-issued session tokens.

With Supabase Auth, signup / login / sessions / password reset / email
verification all happen in the frontend against Supabase directly. The
backend's only job is to *verify* the access token (a JWT) the frontend
attaches to protected requests, and resolve it to a user.

Supabase signs access tokens one of two ways, and this module supports
both automatically by reading each token's `alg` header:

  * HS256        — legacy symmetric signing with the project JWT secret
                   (SUPABASE_JWT_SECRET).
  * ES256 / RS256 — modern asymmetric signing; the public keys are fetched
                    from the project's JWKS endpoint (needs SUPABASE_URL).

No config switch is required — whichever scheme the project uses just works.
"""

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import supabase_admin
from app.config import settings

_bearer = HTTPBearer(auto_error=False)
_AUDIENCE = "authenticated"

# JWKS client for asymmetric tokens. Constructed once; it lazily fetches and
# caches the project's public keys on first use (PyJWT caches for ~5 min).
_jwks_client = None
if settings.SUPABASE_URL:
    _jwks_url = settings.SUPABASE_URL.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    _jwks_client = jwt.PyJWKClient(_jwks_url)


def _decode(token: str) -> dict:
    """Verify a Supabase JWT, choosing HS256 vs ES256/RS256 from its header."""
    alg = jwt.get_unverified_header(token).get("alg", "")

    if alg == "HS256":
        if not settings.SUPABASE_JWT_SECRET:
            raise HTTPException(
                status_code=500,
                detail="SUPABASE_JWT_SECRET is not configured on the server",
            )
        return jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience=_AUDIENCE,
        )

    if alg in ("ES256", "RS256"):
        if _jwks_client is None:
            raise HTTPException(
                status_code=500,
                detail="SUPABASE_URL is not configured on the server",
            )
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience=_AUDIENCE,
        )

    raise HTTPException(
        status_code=401, detail=f"Unsupported token algorithm: {alg or 'none'}"
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """FastAPI dependency: verify the Supabase Bearer token, or raise 401.

    Returns a normalised user dict: id, email, fullName, plan.
    """
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = _decode(creds.credentials)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    user_metadata = payload.get("user_metadata") or {}
    return {
        "id": payload.get("sub"),
        "email": payload.get("email", ""),
        "fullName": user_metadata.get("full_name", ""),
        # `plan` is NOT in the token — it lives in the profiles table. Callers
        # that need it (require_pro) read it from there.
        "plan": "free",
    }


async def require_pro(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency for Pro-only endpoints.

    Verifies the token (via get_current_user), then reads the authoritative
    `plan` from the profiles table and rejects non-Pro users with 403.
    """
    plan = await supabase_admin.get_profile_plan(user["id"])
    if plan != "pro":
        raise HTTPException(
            status_code=403, detail="This feature requires a Pro subscription."
        )
    return {**user, "plan": plan}
