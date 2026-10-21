"""Verifies Supabase-issued bearer tokens and resolves the authenticated user.

FastAPI never trusts a user id supplied by the client (query param, body or otherwise);
every protected route depends on `get_current_user`, which verifies the token's
signature and expiry against the Supabase project's own keys and takes the user id
only from the verified `sub` claim.
"""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Header, HTTPException, Query
from jwt import PyJWKClient

from .config import settings


# Demo accounts that only ever see the frontend's scripted walkthrough (/walkthrough).
# They must never use the real product, so the API refuses them outright.
WALKTHROUGH_EMAILS = {"yc@theopenscientist.com"}


def is_walkthrough_account(email: str | None) -> bool:
    if not email:
        return False
    extra = {e.strip().lower() for e in settings.walkthrough_emails.split(",") if e.strip()}
    return email.strip().lower() in WALKTHROUGH_EMAILS | extra


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str | None


def _unconfigured() -> HTTPException:
    return HTTPException(500, "SUPABASE_URL is not configured on the server")


@lru_cache(maxsize=1)
def _jwks_client() -> PyJWKClient:
    if not settings.supabase_url:
        raise _unconfigured()
    url = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def verify_token(token: str) -> dict:
    """Verify a Supabase access token and return its claims, or raise HTTPException(401)."""
    if not settings.supabase_url:
        raise _unconfigured()
    try:
        if settings.supabase_jwt_secret:
            # Legacy projects that still sign with the shared HS256 secret.
            claims = jwt.decode(
                token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated"
            )
        else:
            # Current default: asymmetric JWT signing keys, verified against the
            # project's published JWKS (fetched once, cached, refreshed on key rotation).
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, signing_key.key, algorithms=["ES256", "RS256"], audience="authenticated"
            )
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired token") from exc
    return claims


async def get_current_user(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
) -> CurrentUser:
    """Reads the bearer token from the Authorization header, or, failing that, a
    `token` query parameter. The query param exists only for the handful of GET
    routes the frontend links to directly (<a>/<img>/<iframe src>), which can't
    attach a custom header; every fetch() call from the app uses the header."""
    bearer = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[len("bearer ") :].strip()
    bearer = bearer or (token or "").strip() or None
    if not bearer:
        raise HTTPException(401, "Missing bearer token")
    claims = verify_token(bearer)
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(401, "Token has no subject")
    if is_walkthrough_account(claims.get("email")):
        raise HTTPException(403, {"code": "walkthrough_only", "message": "This account can only view the walkthrough."})
    return CurrentUser(id=sub, email=claims.get("email"))
