"""The RFC 8693 front door, the on-behalf-of target for AgentCore Identity.

Cognito's token endpoint does not offer the token-exchange grant, so this is the
arrangement of AWS's sample-cognito-oauth2-token-exchange: a small endpoint
implements the grant and a second Cognito user pool, the exchange pool, mints
the token through its custom authentication flow. This Lambda signs nothing
and holds no key. It authenticates the calling client, checks the request
shape, verifies the customer's token (defence in depth, the pool's triggers
verify it again), then runs CUSTOM_AUTH in the exchange pool as the agent's
service user with the customer's token as the challenge answer. What Cognito
issues, with the claims triggers.py adds, is what the gateway trusts.

Three routes on one Lambda behind an HTTP API (TLS only):
  POST /token                         RFC 8693 exchange, client_secret_basic
  GET  /authorize                     always unsupported_response_type
  GET  /.well-known/openid-configuration   read by the OBO provider only

It is still a TEACHING component. The exchange pool, its triggers and this
front door are the demo's own issuer; in production the exchange belongs to
a managed IdP with a supported on-behalf-of integration.
"""

import base64
import binascii
import hashlib
import hmac
import json
import os
import time
import urllib.parse

import boto3
import subject

# --- Configuration, all static, never derived from a request -----------------
# Three client identities, kept distinct:
#   CLIENT_ID / CLIENT_SECRET_ARN   the front door's own OAuth client, which
#                                   AgentCore Identity's provider authenticates
#                                   with (client_secret_basic)
#   the orders app client           the exchange pool's confidential app client,
#                                   one per downstream; its id is the minted
#                                   token's client_id and aud; its secret goes
#                                   into SECRET_HASH on the admin calls
#   the service user                the exchange pool user the flow runs as
# The pool, client and user ids are read from one SSM parameter shared with
# the triggers; the app client's secret from its own Secrets Manager secret.
ISSUER_URL = os.environ["ISSUER_URL"].rstrip("/")
EXCHANGE_JWKS_URL = os.environ["EXCHANGE_JWKS_URL"]
EXCHANGE_CONFIG_PARAMETER = os.environ["EXCHANGE_CONFIG_PARAMETER"]
ORDERS_CLIENT_SECRET_ARN = os.environ["ORDERS_CLIENT_SECRET_ARN"]
ORDERS_SCOPE = os.environ["ORDERS_SCOPE"]
CLIENT_SECRET_ARN = os.environ["CLIENT_SECRET_ARN"]
CLIENT_ID = os.environ["EXCHANGE_CLIENT_ID"]
MAX_BODY_BYTES = 16384
MAX_LIFETIME = 330  # the client is configured for 300 s; a little tolerance, no more

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
JWT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
ACCESS_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
ACCEPTED_SUBJECT_TYPES = {JWT_TOKEN_TYPE, ACCESS_TOKEN_TYPE}
# The request contract is closed: the RFC 8693 parameters, plus client_id,
# which some clients repeat in the body. Anything else is refused, so a
# claim-shaped parameter cannot be mistaken for input by a later change.
KNOWN_FIELDS = frozenset({
    "grant_type", "subject_token", "subject_token_type", "requested_token_type",
    "scope", "resource", "audience", "actor_token", "actor_token_type", "client_id",
})


def _check_config():
    problems = []
    if not subject._valid_https(ISSUER_URL):
        problems.append("ISSUER_URL must be a clean https URL")
    if not subject._valid_https(EXCHANGE_JWKS_URL):
        problems.append("EXCHANGE_JWKS_URL must be a clean https URL")
    if not EXCHANGE_CONFIG_PARAMETER or not ORDERS_CLIENT_SECRET_ARN.startswith("arn:aws:secretsmanager:"):
        problems.append("exchange pool configuration must be set")
    if CLIENT_SECRET_ARN == ORDERS_CLIENT_SECRET_ARN:
        problems.append("the front door's secret and the app client's secret must differ")
    if problems:
        raise RuntimeError("invalid exchange-service configuration: " + "; ".join(problems))


_check_config()

_cognito = boto3.client("cognito-idp")
_secrets = boto3.client("secretsmanager")
_ssm = boto3.client("ssm")
_CACHE_TTL = 300
_cache = {}


def _cached(name, load):
    now = time.monotonic()
    hit = _cache.get(name)
    if hit is None or now - hit[1] > _CACHE_TTL:
        hit = (load(), now)
        _cache[name] = hit
    return hit[0]


def _secret_field(arn, field) -> str:
    obj = json.loads(_secrets.get_secret_value(SecretId=arn)["SecretString"])
    value = obj.get(field)
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{field} misconfigured")
    return value


def pool_config() -> dict:
    def load():
        cfg = json.loads(_ssm.get_parameter(Name=EXCHANGE_CONFIG_PARAMETER)["Parameter"]["Value"])
        for key in ("pool_id", "client_id", "service_user"):
            if not isinstance(cfg.get(key), str) or not cfg[key]:
                raise RuntimeError("exchange configuration incomplete")
        return cfg
    return _cached("pool", load)


# --- Small helpers ------------------------------------------------------------
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


# --- Client authentication (client_secret_basic), constant time, short TTL ---
def _client_secret() -> str:
    return _cached("front_door_secret", lambda: _secret_field(CLIENT_SECRET_ARN, "client_secret"))


def _orders_client_secret() -> str:
    return _cached("orders_client_secret", lambda: _secret_field(ORDERS_CLIENT_SECRET_ARN, "client_secret"))


def _secret_hash(username: str, client_id: str) -> str:
    """Cognito's SECRET_HASH for a confidential app client: HMAC-SHA256(secret, username + client_id)."""
    mac = hmac.new(_orders_client_secret().encode(), (username + client_id).encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


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


def exchange_in_pool(subject_token: str) -> dict:
    """Run the exchange pool's custom flow. Returns Cognito's AuthenticationResult or raises."""
    cfg = pool_config()
    pool, client, user = cfg["pool_id"], cfg["client_id"], cfg["service_user"]
    secret_hash = _secret_hash(user, client)  # the app client is confidential
    started = _cognito.admin_initiate_auth(
        UserPoolId=pool, ClientId=client, AuthFlow="CUSTOM_AUTH",
        AuthParameters={"USERNAME": user, "SECRET_HASH": secret_hash},
    )
    if started.get("ChallengeName") != "CUSTOM_CHALLENGE" or not started.get("Session"):
        raise RuntimeError("exchange pool did not issue the challenge")
    answered = _cognito.admin_respond_to_auth_challenge(
        UserPoolId=pool, ClientId=client, ChallengeName="CUSTOM_CHALLENGE",
        Session=started["Session"],
        ChallengeResponses={"USERNAME": user, "ANSWER": subject_token, "SECRET_HASH": secret_hash},
        # The verify trigger requires ANSWER to equal this copy, and the
        # pre-token trigger re-verifies it; Cognito passes it through unvalidated.
        # DEMO COMPROMISE, as in the AWS sample: Cognito's API reference says not
        # to send sensitive information in ClientMetadata (it is not stored,
        # validated or encrypted by Cognito), and a bearer token is sensitive.
        # A real exchange passes a single-use handle here and has the verify
        # trigger write the verified claims to a short-lived encrypted record
        # that the pre-token trigger consumes once.
        ClientMetadata={"subject_token": subject_token, "grant": TOKEN_EXCHANGE_GRANT},
    )
    result = answered.get("AuthenticationResult") or {}
    token = result.get("AccessToken")
    if not isinstance(token, str) or not token:
        raise RuntimeError("exchange pool issued no access token")
    # The lifetime is the app client's configuration, which this code cannot
    # cap. Refuse to hand out a token that is longer than configured, so a
    # drifted client setting fails loudly rather than issuing hour-long tokens.
    expires_in = result.get("ExpiresIn")
    if not isinstance(expires_in, int) or not 0 < expires_in <= MAX_LIFETIME:
        raise RuntimeError("exchange pool issued an unexpected lifetime")
    if _unverified_lifetime(token) > MAX_LIFETIME:
        raise RuntimeError("exchange pool issued an unexpected lifetime")
    return result


def _unverified_lifetime(token: str) -> int:
    """exp - iat from the payload, without verifying: Cognito signed it, the gateway verifies it."""
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return int(claims["exp"]) - int(claims["iat"])


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
        body_client_id = _single(form, "client_id")
    except ValueError:
        return _oauth_error(400, "invalid_request", "malformed parameters")

    if grant_type != TOKEN_EXCHANGE_GRANT:
        return _oauth_error(400, "unsupported_grant_type")
    if not set(form) <= KNOWN_FIELDS:
        return _oauth_error(400, "invalid_request", "unknown parameter")
    if body_client_id is not None and body_client_id != CLIENT_ID:
        return _oauth_error(400, "invalid_request", "client_id mismatch")
    if actor_token is not None or "actor_token_type" in form:  # no actor: reject delegation controls
        return _oauth_error(400, "invalid_request", "actor_token not supported")
    if not subject_token:
        return _oauth_error(400, "invalid_request", "subject_token required")
    if subject_token_type not in ACCEPTED_SUBJECT_TYPES:
        return _oauth_error(400, "invalid_request", "unsupported subject_token_type")
    if requested_token_type is not None and requested_token_type != ACCESS_TOKEN_TYPE:
        return _oauth_error(400, "invalid_request", "unsupported requested_token_type")
    if scope is not None and scope != ORDERS_SCOPE:  # exactly the one scope, or omit
        return _oauth_error(400, "invalid_scope")
    orders_client_id = pool_config()["client_id"]  # the audience is the app client
    if resource is not None and resource != orders_client_id:
        return _oauth_error(400, "invalid_target")
    if audience is not None and audience != orders_client_id:
        return _oauth_error(400, "invalid_target")
    print("token request fields:", sorted(form))  # names only, never values

    # Fail fast on a bad subject before spending a Cognito flow on it. The
    # pool's triggers verify independently; this check cannot mint anything.
    try:
        subject.validate(subject_token)
    except Exception as exc:  # noqa: BLE001 — any validation failure is a uniform rejection
        print("subject token rejected:", type(exc).__name__)  # the class, never the token
        return _oauth_error(400, "invalid_grant", "subject token rejected")

    try:
        result = exchange_in_pool(subject_token)
    except Exception as exc:  # noqa: BLE001 — a refused flow is an invalid grant; say nothing more
        # The error class and Cognito's error code are operational, not secret.
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "") if hasattr(exc, "response") else ""
        print("exchange flow refused:", type(exc).__name__, code)
        return _oauth_error(400, "invalid_grant", "subject token rejected")

    return _resp(200, {
        "access_token": result["AccessToken"],  # the ID and refresh tokens are dropped
        "issued_token_type": ACCESS_TOKEN_TYPE,
        "token_type": "Bearer",
        "expires_in": int(result.get("ExpiresIn") or 0),
        "scope": ORDERS_SCOPE,
    })


# --- discovery, for the OBO credential provider ---------------------------------
def handle_authorize(_event) -> dict:
    return _oauth_error(400, "unsupported_response_type",
                        "this issuer performs token exchange only")


def handle_discovery(_event) -> dict:
    # Read by AgentCore Identity's credential provider to find token_endpoint.
    # The gateway does not read this; it validates the minted token against
    # the exchange pool's own discovery document. The OIDC-required fields
    # are advertised so the document parses as a provider document; the
    # authorization endpoint answers unsupported_response_type.
    return _resp(200, {
        "issuer": ISSUER_URL,
        "authorization_endpoint": f"{ISSUER_URL}/authorize",
        "token_endpoint": f"{ISSUER_URL}/token",
        "jwks_uri": EXCHANGE_JWKS_URL,
        "grant_types_supported": [TOKEN_EXCHANGE_GRANT],
        "token_endpoint_auth_methods_supported": ["client_secret_basic"],
        "scopes_supported": [ORDERS_SCOPE],
        "id_token_signing_alg_values_supported": ["RS256"],
        "response_types_supported": ["token"],
        "subject_types_supported": ["public"],
    })


# --- router -------------------------------------------------------------------
_ROUTES = {
    ("POST", "/token"): handle_token,
    ("GET", "/authorize"): handle_authorize,
    ("GET", "/.well-known/openid-configuration"): handle_discovery,
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
