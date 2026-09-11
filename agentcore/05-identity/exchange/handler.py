"""A minimal RFC 8693 token-exchange service, the on-behalf-of target for
AgentCore Identity. Cognito can't be an exchange target, so this stands in for
what a managed IdP (Entra, Auth0) would do. It is a TEACHING component: it is a
token issuer, which is crown-jewel infrastructure. Compromise of this code or
its signing role is total issuer compromise. KMS keeps the private key from
being exported; it does NOT stop this process, once trusted, signing a token
for any customer. In production you would use a managed IdP, not this.

Three routes on one Lambda behind an HTTP API (TLS only):
  POST /token                         RFC 8693 exchange, client_secret_basic
  GET  /.well-known/openid-configuration
  GET  /.well-known/jwks.json

AgentCore Identity sends the customer's Cognito access token as subject_token
with the registered client's basic auth. We verify that Cognito token strictly,
then mint a short-lived ES256 token (signed by KMS) scoped to the order gateway
carrying the verified username. The gateway trusts this issuer; Cedar still
enforces username == customer_id.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request

import boto3
import jwt
from cryptography.hazmat.primitives.asymmetric.ec import (
    SECP256R1,
    EllipticCurvePublicKey,
)
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
)

# --- Configuration, all static, never derived from a request -----------------
COGNITO_ISSUER = os.environ["COGNITO_ISSUER"].rstrip("/")
COGNITO_JWKS_URL = os.environ["COGNITO_JWKS_URL"]
ALLOWED_CLIENT_IDS = frozenset(c for c in os.environ["ALLOWED_CLIENT_IDS"].split(",") if c)
ISSUER_URL = os.environ["ISSUER_URL"].rstrip("/")
ORDERS_AUDIENCE = os.environ["ORDERS_AUDIENCE"]
ORDERS_SCOPE = os.environ["ORDERS_SCOPE"]
KMS_KEY_ARN = os.environ["KMS_KEY_ID"]  # must be the immutable key ARN, not an alias
CLIENT_SECRET_ARN = os.environ["CLIENT_SECRET_ARN"]
CLIENT_ID = os.environ["EXCHANGE_CLIENT_ID"]
MAX_TTL = int(os.environ.get("MAX_TTL_SECONDS", "300"))
MIN_REMAINING = int(os.environ.get("MIN_REMAINING_SECONDS", "30"))
MAX_SUBJECT_AGE = int(os.environ.get("MAX_SUBJECT_AGE_SECONDS", "3600"))
LEEWAY = 60
MAX_JWKS_BYTES = 1_000_000
MAX_BODY_BYTES = 16384

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
JWT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
ACCEPTED_SUBJECT_TYPES = {JWT_TOKEN_TYPE, ACCESS_TOKEN_TYPE}


def _valid_https(url: str) -> bool:
    p = urllib.parse.urlsplit(url)
    return (p.scheme == "https" and bool(p.hostname)
            and not p.username and not p.password and not p.query and not p.fragment)


def _check_config():
    """A configuration typo must fail startup, not become total compromise."""
    problems = []
    if not _valid_https(COGNITO_ISSUER):
        problems.append("COGNITO_ISSUER must be a clean https URL")
    if not _valid_https(ISSUER_URL):
        problems.append("ISSUER_URL must be a clean https URL")
    if COGNITO_JWKS_URL != COGNITO_ISSUER + "/.well-known/jwks.json":
        problems.append("COGNITO_JWKS_URL must be the issuer's well-known jwks path")
    if not ALLOWED_CLIENT_IDS:
        problems.append("ALLOWED_CLIENT_IDS is empty")
    if not KMS_KEY_ARN.startswith("arn:aws:kms:"):
        problems.append("KMS_KEY_ID must be the immutable key ARN")
    if MAX_TTL <= 0 or MIN_REMAINING < 0 or MIN_REMAINING >= MAX_TTL:
        problems.append("bad TTL configuration")
    if problems:
        raise RuntimeError("invalid exchange-service configuration: " + "; ".join(problems))


_check_config()

_kms = boto3.client("kms")
_secrets = boto3.client("secretsmanager")


# --- Small helpers ------------------------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _resp(status, body, headers=None):
    base = {"Cache-Control": "no-store", "Pragma": "no-cache", "Content-Type": "application/json"}
    if headers:
        base.update(headers)
    return {"statusCode": status, "headers": base, "body": json.dumps(body)}


def _oauth_error(status, code, description="", headers=None):
    body = {"error": code}
    if description:
        body["error_description"] = description
    return _resp(status, body, headers)


# --- Cognito JWKS: pinned URL, no redirects, validate-before-replace ---------
_jwks_cache = {"keys": None, "at": 0.0, "last_refresh": 0.0}
_JWKS_TTL = 3600
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
    return _find_kid(keys or [], kid)


def _find_kid(keys, kid):
    matches = [k for k in keys if k.get("kid") == kid]
    return matches[0] if len(matches) == 1 else None


# --- Subject-token validation (the Cognito access token) ----------------------
def _require_int(claims, name, required=True):
    v = claims.get(name)
    if v is None:
        if required:
            raise ValueError(f"missing {name}")
        return None
    if type(v) is not int:  # PyJWT can coerce numeric strings; be strict
        raise ValueError(f"{name} not an integer")
    return v


def validate_subject_token(token: str) -> dict:
    if not token or len(token) > 8192 or token.count(".") != 2:
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


# --- KMS ES256 signer, bound to the immutable key ARN -------------------------
_signing = {"kid": None, "jwk": None}


def _load_public_key():
    if _signing["kid"] is not None:
        return
    pub = load_der_public_key(_kms.get_public_key(KeyId=KMS_KEY_ARN)["PublicKey"])
    if not isinstance(pub, EllipticCurvePublicKey) or not isinstance(pub.curve, SECP256R1):
        raise RuntimeError("signing key is not P-256")  # noqa: TRY004 — a deploy/config error
    spki = pub.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    kid = _b64url(hashlib.sha256(spki).digest())
    nums = pub.public_numbers()
    _signing["kid"] = kid
    _signing["jwk"] = {
        "kty": "EC", "crv": "P-256", "use": "sig", "alg": "ES256", "kid": kid,
        "x": _b64url(nums.x.to_bytes(32, "big")),  # P-256 coords are exactly 32 octets
        "y": _b64url(nums.y.to_bytes(32, "big")),
    }


def _der_to_jose(der_sig: bytes) -> bytes:
    r, s = decode_dss_signature(der_sig)
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def sign_jwt(claims: dict) -> str:
    _load_public_key()
    header = {"alg": "ES256", "typ": "JWT", "kid": _signing["kid"]}
    signing_input = (_b64url(json.dumps(header, separators=(",", ":")).encode())
                     + "." + _b64url(json.dumps(claims, separators=(",", ":")).encode()))
    digest = hashlib.sha256(signing_input.encode("ascii")).digest()
    out = _kms.sign(KeyId=KMS_KEY_ARN, Message=digest, MessageType="DIGEST",
                    SigningAlgorithm="ECDSA_SHA_256")
    if out.get("KeyId") not in (KMS_KEY_ARN,):  # signed by the key we published, nothing else
        raise RuntimeError("unexpected signing key id")
    return signing_input + "." + _b64url(_der_to_jose(out["Signature"]))


# --- Client authentication (client_secret_basic), constant time, short TTL ---
_secret_cache = {"value": None, "at": 0.0}
_SECRET_TTL = 300


def _client_secret() -> str:
    now = time.monotonic()
    if _secret_cache["value"] is None or now - _secret_cache["at"] > _SECRET_TTL:
        raw = _secrets.get_secret_value(SecretId=CLIENT_SECRET_ARN)["SecretString"]
        obj = json.loads(raw)
        secret = obj.get("client_secret")
        if not isinstance(secret, str) or not secret:
            raise RuntimeError("client secret misconfigured")
        _secret_cache["value"] = secret
        _secret_cache["at"] = now
    return _secret_cache["value"]


def _check_client_auth(headers: dict) -> bool:
    auth = headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[6:].strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError):
        return False
    if ":" not in decoded:
        return False
    cid, secret = decoded.split(":", 1)
    # RFC 6749 form-urlencodes the components before base64; our id/secret are
    # unreserved characters, so decoding is a no-op, but do it for correctness.
    cid = urllib.parse.unquote_plus(cid)
    secret = urllib.parse.unquote_plus(secret)
    try:
        expected = _client_secret()
    except Exception:  # noqa: BLE001 — any failure denies
        return False
    ok_id = hmac.compare_digest(hashlib.sha256(cid.encode()).digest(),
                                hashlib.sha256(CLIENT_ID.encode()).digest())
    ok_secret = hmac.compare_digest(hashlib.sha256(secret.encode()).digest(),
                                    hashlib.sha256(expected.encode()).digest())
    return ok_id and ok_secret


# --- /token -------------------------------------------------------------------
_CHALLENGE = {"WWW-Authenticate": 'Basic realm="token-exchange"'}


def _decode_body(event) -> str:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(body, validate=True)
        if len(raw) > MAX_BODY_BYTES:
            raise ValueError("body too large")
        return raw.decode("utf-8")  # strict: invalid utf-8 raises
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ValueError("body too large")
    return body


def _single(form, name):
    vals = form.get(name)
    if vals is None:
        return None
    if len(vals) != 1:
        raise ValueError(f"duplicate {name}")
    return vals[0]


def handle_token(event) -> dict:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    # Cheap structural checks first, before touching the secret store.
    ctype = headers.get("content-type", "").split(";", 1)[0].strip()
    if ctype != "application/x-www-form-urlencoded":
        return _oauth_error(400, "invalid_request", "form encoding required")
    try:
        body = _decode_body(event)
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return _oauth_error(400, "invalid_request", "bad request body")

    if not _check_client_auth(headers):
        return _oauth_error(401, "invalid_client", headers=_CHALLENGE)

    try:
        form = urllib.parse.parse_qs(body, strict_parsing=bool(body), keep_blank_values=True,
                                     max_num_fields=25)
        grant_type = _single(form, "grant_type")
        subject_token = _single(form, "subject_token")
        subject_token_type = _single(form, "subject_token_type")
        requested_token_type = _single(form, "requested_token_type")
        scope = _single(form, "scope")
        resource = _single(form, "resource")
        audience = _single(form, "audience")
        actor_token = _single(form, "actor_token")
    except ValueError:
        return _oauth_error(400, "invalid_request", "malformed parameters")

    if grant_type != TOKEN_EXCHANGE_GRANT:
        return _oauth_error(400, "unsupported_grant_type")
    if actor_token is not None:  # we assert no actor; reject unsupported delegation controls
        return _oauth_error(400, "invalid_request", "actor_token not supported")
    if not subject_token:
        return _oauth_error(400, "invalid_request", "subject_token required")
    if subject_token_type not in ACCEPTED_SUBJECT_TYPES:
        return _oauth_error(400, "invalid_request", "unsupported subject_token_type")
    if requested_token_type is not None and requested_token_type != ACCESS_TOKEN_TYPE:
        return _oauth_error(400, "invalid_request", "unsupported requested_token_type")
    if scope is not None and scope != ORDERS_SCOPE:  # exactly the one scope, or omit
        return _oauth_error(400, "invalid_scope")
    if resource is not None and resource != ORDERS_AUDIENCE:
        return _oauth_error(400, "invalid_target")
    if audience is not None and audience != ORDERS_AUDIENCE:
        return _oauth_error(400, "invalid_target")

    try:
        subject = validate_subject_token(subject_token)
    except Exception:  # noqa: BLE001 — any validation failure is a uniform rejection
        return _oauth_error(400, "invalid_grant", "subject token rejected")

    now = int(time.time())
    exp = min(now + MAX_TTL, int(subject["exp"]))
    if exp - now < MIN_REMAINING:
        return _oauth_error(400, "invalid_grant", "subject token rejected")

    claims = {
        "iss": ISSUER_URL, "aud": ORDERS_AUDIENCE,
        "sub": subject["sub"], "username": subject["username"],
        "scope": ORDERS_SCOPE,
        "act": {"client_id": CLIENT_ID},  # the registered client, NOT a workload identity
        "iat": now, "exp": exp, "jti": _b64url(os.urandom(16)),
    }
    return _resp(200, {
        "access_token": sign_jwt(claims),
        "issued_token_type": ACCESS_TOKEN_TYPE,
        "token_type": "Bearer",
        "expires_in": exp - now,
        "scope": ORDERS_SCOPE,
    })


# --- discovery + jwks ---------------------------------------------------------
def handle_discovery(_event) -> dict:
    return _resp(200, {
        "issuer": ISSUER_URL,
        "token_endpoint": f"{ISSUER_URL}/token",
        "jwks_uri": f"{ISSUER_URL}/.well-known/jwks.json",
        "grant_types_supported": [TOKEN_EXCHANGE_GRANT],
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
        "scopes_supported": [ORDERS_SCOPE],
        "id_token_signing_alg_values_supported": ["ES256"],
        "response_types_supported": ["token"],
        "subject_types_supported": ["public"],
    })


def handle_jwks(_event) -> dict:
    _load_public_key()
    return _resp(200, {"keys": [_signing["jwk"]]})


# --- router -------------------------------------------------------------------
_ROUTES = {
    ("POST", "/token"): handle_token,
    ("GET", "/.well-known/openid-configuration"): handle_discovery,
    ("GET", "/.well-known/jwks.json"): handle_jwks,
}


def lambda_handler(event, _context):
    ctx = event.get("requestContext", {}).get("http", {})
    handler = _ROUTES.get((ctx.get("method", ""), ctx.get("path", "")))
    if handler is None:
        return _oauth_error(404, "not_found")
    try:
        return handler(event)
    except Exception:  # noqa: BLE001 — fail closed, leak nothing
        return _oauth_error(500, "server_error")
