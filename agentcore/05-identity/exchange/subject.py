"""Strict validation of the customer's Cognito access token, the RFC 8693 subject.

Shared by the exchange front door (fail fast, defence in depth) and by the
exchange pool's triggers (the verification that actually gates minting). The
rules are the same everywhere: RS256 only, no key-bearing headers, the pool's
issuer pinned, an access token from an allowlisted client, sane times, and a
JWKS cache that is validated before it replaces the last good document and is
served stale for a bounded period only.
"""

import json
import os
import time
import urllib.parse
import urllib.request

import jwt

COGNITO_ISSUER = os.environ["COGNITO_ISSUER"].rstrip("/")
COGNITO_JWKS_URL = os.environ["COGNITO_JWKS_URL"]
ALLOWED_CLIENT_IDS = frozenset(c for c in os.environ["ALLOWED_CLIENT_IDS"].split(",") if c)
MAX_SUBJECT_AGE = int(os.environ.get("MAX_SUBJECT_AGE_SECONDS", "3600"))
LEEWAY = 60
MAX_JWKS_BYTES = 1_000_000
MAX_TOKEN_CHARS = 8192


def _valid_https(url: str) -> bool:
    p = urllib.parse.urlsplit(url)
    return (p.scheme == "https" and bool(p.hostname)
            and not p.username and not p.password and not p.query and not p.fragment)


def check_config():
    """A configuration typo must fail startup, not become an open verifier."""
    problems = []
    if not _valid_https(COGNITO_ISSUER):
        problems.append("COGNITO_ISSUER must be a clean https URL")
    if COGNITO_JWKS_URL != COGNITO_ISSUER + "/.well-known/jwks.json":
        problems.append("COGNITO_JWKS_URL must be the issuer's well-known jwks path")
    if not ALLOWED_CLIENT_IDS:
        problems.append("ALLOWED_CLIENT_IDS is empty")
    if MAX_SUBJECT_AGE <= 0:
        problems.append("bad MAX_SUBJECT_AGE_SECONDS")
    if problems:
        raise RuntimeError("invalid subject-validation configuration: " + "; ".join(problems))


check_config()


# --- Cognito JWKS: pinned URL, no redirects, validate-before-replace ---------
# A cached document is fresh for _JWKS_TTL and is served on refresh failure
# for at most _JWKS_MAX_STALE after it was fetched. Past that, subject tokens
# are refused until a refresh succeeds, so a retired Cognito key is never
# trusted indefinitely just because the JWKS endpoint became unreachable.
_jwks_cache = {"keys": None, "at": 0.0, "last_refresh": 0.0}
_JWKS_TTL = 3600
_JWKS_MAX_STALE = 6 * 3600
_JWKS_MIN_REFRESH_GAP = 30


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # a JWKS URL that redirects is not trusted
        return None


def _fetch_jwks():
    req = urllib.request.Request(COGNITO_JWKS_URL, headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(req, timeout=3) as r:
        raw = r.read(MAX_JWKS_BYTES + 1)
    if len(raw) > MAX_JWKS_BYTES:
        raise ValueError("JWKS document too large")
    doc = json.loads(raw)
    keys = doc.get("keys")
    if not isinstance(keys, list) or not (1 <= len(keys) <= 20):
        raise ValueError("invalid JWKS document")
    seen, valid = set(), []
    for k in keys:
        kid = k.get("kid")
        if (not isinstance(kid, str) or not (1 <= len(kid) <= 128) or kid in seen
                or k.get("kty") != "RSA" or not isinstance(k.get("n"), str)
                or not isinstance(k.get("e"), str)):
            raise ValueError("invalid JWK entry")
        if k.get("use", "sig") != "sig" or (k.get("alg") and k["alg"] != "RS256"):
            raise ValueError("unexpected JWK use/alg")
        if any(p in k for p in ("d", "p", "q", "dp", "dq", "qi")):
            raise ValueError("private material in JWKS")
        seen.add(kid)
        valid.append(k)
    return valid  # only replace the cache once the whole document validates


def _jwk_for_kid(kid):
    now = time.monotonic()
    keys = _jwks_cache["keys"]
    if keys is not None and now - _jwks_cache["at"] < _JWKS_TTL:
        hit = _find_kid(keys, kid)
        if hit is not None:
            return hit
    if now - _jwks_cache["last_refresh"] >= _JWKS_MIN_REFRESH_GAP:
        _jwks_cache["last_refresh"] = now
        try:
            fresh = _fetch_jwks()
            _jwks_cache["keys"] = fresh
            _jwks_cache["at"] = now
            keys = fresh
        except Exception:  # noqa: BLE001, S110 — fail safe: keep validated last-known-good
            pass
    if keys is None or now - _jwks_cache["at"] > _JWKS_MAX_STALE:
        return None  # nothing trustworthy to validate against; refuse
    return _find_kid(keys, kid)


def _find_kid(keys, kid):
    matches = [k for k in keys if k.get("kid") == kid]
    return matches[0] if len(matches) == 1 else None


# --- The validator --------------------------------------------------------------
def _require_int(claims, name, required=True):
    v = claims.get(name)
    if v is None:
        if required:
            raise ValueError(f"missing {name}")
        return None
    if type(v) is not int:  # PyJWT can coerce numeric strings; be strict
        raise ValueError(f"{name} not an integer")
    return v


def validate(token, min_remaining=30) -> dict:
    """Verified claims of a customer's access token, or ValueError. Never logs the token.

    Signature verification allows LEEWAY seconds of clock skew on exp, so a
    separate, leeway-free check requires at least min_remaining seconds of life
    left: a token that is expired or about to expire must not be exchanged for a
    fresh one, because Cognito cannot cap the minted token to the subject's exp.
    """
    if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_CHARS or token.count(".") != 2:
        raise ValueError("malformed token")
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256":
        raise ValueError("unexpected alg")
    for banned in ("jku", "x5u", "jwk", "x5c", "crit", "b64"):
        if banned in header:
            raise ValueError("disallowed header")
    kid = header.get("kid")
    if not isinstance(kid, str) or not (1 <= len(kid) <= 128):
        raise ValueError("bad kid")
    jwk = _jwk_for_kid(kid)
    if jwk is None:
        raise ValueError("unknown key")
    key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(jwk))
    claims = jwt.decode(
        token, key=key, algorithms=["RS256"], issuer=COGNITO_ISSUER, leeway=LEEWAY,
        options={"require": ["exp", "iat", "iss", "sub"], "verify_aud": False},
    )
    now = int(time.time())
    exp = _require_int(claims, "exp")
    iat = _require_int(claims, "iat")
    _require_int(claims, "nbf", required=False)
    if iat > now + LEEWAY or iat > exp or exp - iat > MAX_SUBJECT_AGE:
        raise ValueError("implausible token times")
    if exp - now < min_remaining:
        raise ValueError("subject token expired or about to")
    if claims.get("token_use") != "access":
        raise ValueError("not an access token")
    if claims.get("client_id") not in ALLOWED_CLIENT_IDS:
        raise ValueError("client_id not allowed")
    sub, username = claims.get("sub"), claims.get("username")
    if not isinstance(sub, str) or not sub:
        raise ValueError("missing sub")
    if not isinstance(username, str) or not username:
        raise ValueError("missing username")
    return claims
