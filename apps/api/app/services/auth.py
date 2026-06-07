"""Supabase JWT auth dependency.

Two verification paths, picked at runtime per token:

  1. **JWKS (recommended)** — fetched from
     `<SUPABASE_URL>/auth/v1/.well-known/jwks.json`. Used when the token
     header has a `kid` claim. Modern Supabase projects use ES256 / RS256
     asymmetric signing; the public key set is cached for 10 minutes.

  2. **HS256 shared secret** — used only when `SUPABASE_JWT_SECRET` is set
     in the environment. Legacy projects only.

Network calls are minimised: JWKS is fetched once per process (lazily) and
re-fetched if a token's `kid` is not in the cache. The cache TTL is 10 min.
"""
from __future__ import annotations

import os
import time
from typing import Annotated

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import settings


_JWKS_CACHE: dict | None = None
_JWKS_CACHED_AT: float = 0.0
_JWKS_TTL_SECONDS = 600  # match Supabase edge cache (10 min)
# Tolerate small clock drift between Supabase auth server and our API host.
# 10s is enough to absorb typical NTP drift without weakening auth meaningfully.
_CLOCK_SKEW_LEEWAY_SECONDS = 10


def _jwt_secret() -> str | None:
    return os.getenv("SUPABASE_JWT_SECRET") or None


async def _fetch_jwks(force: bool = False) -> dict:
    """Fetch and cache the project's JWKS. Refreshes when stale."""
    global _JWKS_CACHE, _JWKS_CACHED_AT
    now = time.time()
    fresh = _JWKS_CACHE is not None and now - _JWKS_CACHED_AT < _JWKS_TTL_SECONDS
    if fresh and not force:
        return _JWKS_CACHE  # type: ignore[return-value]

    if not settings.supabase_url:
        raise HTTPException(status_code=500, detail="SUPABASE_URL not configured")

    url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    headers: dict[str, str] = {}
    if settings.supabase_anon_key:
        # Some projects gate JWKS behind apikey; pass anon to be safe
        headers["apikey"] = settings.supabase_anon_key
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
    _JWKS_CACHE = data
    _JWKS_CACHED_AT = now
    return data


def _public_key_from_jwk(jwk: dict):
    """Build a verification key for any supported alg (RSA / EC / OKP)."""
    kty = jwk.get("kty")
    if kty == "RSA":
        return jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
    if kty == "EC":
        return jwt.algorithms.ECAlgorithm.from_jwk(jwk)
    if kty == "OKP":
        return jwt.algorithms.OKPAlgorithm.from_jwk(jwk)
    raise jwt.InvalidTokenError(f"unsupported kty: {kty}")


async def _decode_jwks(token: str, header: dict) -> dict:
    kid = header.get("kid")
    alg = header.get("alg", "RS256")
    jwks = await _fetch_jwks()
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        # Force-refresh in case keys were rotated since last cache
        jwks = await _fetch_jwks(force=True)
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if not key:
        raise jwt.InvalidTokenError(f"kid {kid} not in JWKS")

    public_key = _public_key_from_jwk(key)
    return jwt.decode(
        token,
        public_key,
        algorithms=[alg],
        audience="authenticated",
        options={"verify_aud": True},
        leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
    )


async def _decode(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    alg = header.get("alg", "")

    # HS256 path: only if a secret is configured AND header says HS256
    secret = _jwt_secret()
    if alg == "HS256" and secret:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_aud": True},
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
        )

    # JWKS path: any asymmetric alg with a kid
    if header.get("kid"):
        return await _decode_jwks(token, header)

    raise jwt.InvalidTokenError(
        "Token has no kid and no shared secret is configured. "
        "Either set SUPABASE_JWT_SECRET or use a token signed with an "
        "asymmetric key (kid present)."
    )


async def current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = await _decode(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Auth verification failed: {e}")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")
    return user_id


CurrentUser = Annotated[str, Depends(current_user_id)]
