"""驗證 Google 簽發的 ID token。不讀 Gmail，也不使用 client secret。"""

from __future__ import annotations

import json
import time
import urllib.request
from typing import Any, Dict, Sequence

import jwt
from jwt.algorithms import RSAAlgorithm

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
_CLOCK_SKEW_SECONDS = 30
_MAX_TOKEN_LENGTH = 8192
_JWKS_TTL_SECONDS = 3600

_jwks_cache: Dict[str, Any] = {"fetched_at": 0.0, "keys": {}}


class GoogleTokenError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def load_jwks(force: bool = False) -> Dict[str, Dict[str, Any]]:
    now = time.time()
    cached = _jwks_cache["keys"]
    if not force and cached and now - float(_jwks_cache["fetched_at"]) < _JWKS_TTL_SECONDS:
        return cached
    try:
        with urllib.request.urlopen(GOOGLE_JWKS_URL, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        if cached and not force:
            return cached
        raise GoogleTokenError("jwks") from exc
    keys: Dict[str, Dict[str, Any]] = {}
    for item in payload.get("keys") or []:
        kid = item.get("kid")
        if isinstance(kid, str) and kid:
            keys[kid] = item
    if not keys:
        raise GoogleTokenError("jwks")
    _jwks_cache["keys"] = keys
    _jwks_cache["fetched_at"] = now
    return keys


def verify_google_id_token(token: str, *, audiences: Sequence[str]) -> str:
    """驗過簽章、iss、aud、exp 與 email_verified 後，回傳正規化 email。不回傳 sub。"""
    if not audiences:
        raise GoogleTokenError("not_configured")
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH or token.count(".") != 2:
        raise GoogleTokenError("malformed")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise GoogleTokenError("malformed") from exc
    if header.get("alg") != "RS256":
        raise GoogleTokenError("algorithm")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise GoogleTokenError("malformed")
    key = _key_for_kid(kid)
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=list(audiences),
            issuer=list(GOOGLE_ISSUERS),
            leeway=_CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "email"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise GoogleTokenError("expired") from exc
    except jwt.InvalidAudienceError as exc:
        raise GoogleTokenError("audience") from exc
    except jwt.InvalidIssuerError as exc:
        raise GoogleTokenError("issuer") from exc
    except jwt.InvalidTokenError as exc:
        raise GoogleTokenError("signature") from exc
    if payload.get("email_verified") is not True:
        raise GoogleTokenError("email_verified")
    email = str(payload.get("email") or "").strip().lower()
    if "@" not in email or any(char.isspace() for char in email):
        raise GoogleTokenError("email")
    return email


def _key_for_kid(kid: str) -> Any:
    keys = load_jwks()
    jwk = keys.get(kid)
    if jwk is None:
        keys = load_jwks(force=True)
        jwk = keys.get(kid)
    if jwk is None:
        raise GoogleTokenError("signature")
    return RSAAlgorithm.from_jwk(json.dumps(jwk))
