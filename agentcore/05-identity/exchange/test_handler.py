"""The RFC 8693 front door: client auth, the request contract, and what it hands the exchange pool.

Cognito, Secrets Manager and SSM are stubbed. The pool's own behaviour is
test_triggers.py; here the pool is a recorder that returns a canned token.
"""

import base64
import hashlib
import hmac
import json
import urllib.parse

import handler
import pytest
from conftest import POOL, customer_token

SECRET = "shared-secret"
POOL_SECRET = "orders-client-secret-value"


def _cognito_like(lifetime=300):
    """An unsigned token with a real payload, as the stub pool's AccessToken."""
    import time
    now = int(time.time())
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return b({"alg": "RS256", "kid": "k"}) + "." + b({"iat": now, "exp": now + lifetime}) + ".sig"


MINTED = _cognito_like()


class _Pool:
    """Stands in for cognito-idp: records the admin calls, issues a canned token."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def admin_initiate_auth(self, **kw):
        self.calls.append(("initiate", kw))
        if self.fail == "initiate":
            raise RuntimeError("NotAuthorizedException")
        return {"ChallengeName": "CUSTOM_CHALLENGE", "Session": "session-1"}

    def admin_respond_to_auth_challenge(self, **kw):
        self.calls.append(("respond", kw))
        if self.fail == "respond":
            raise RuntimeError("NotAuthorizedException")
        if self.fail == "no-token":
            return {"ChallengeName": "CUSTOM_CHALLENGE", "Session": "session-2"}
        if self.fail == "long":
            return {"AuthenticationResult": {"AccessToken": _cognito_like(3600), "ExpiresIn": 3600}}
        if self.fail == "long-token":
            return {"AuthenticationResult": {"AccessToken": _cognito_like(3600), "ExpiresIn": 300}}
        return {"AuthenticationResult": {"AccessToken": MINTED, "IdToken": "id.tok.en",
                                         "RefreshToken": "refresh", "ExpiresIn": 300}}


def _wire(monkeypatch, p):
    monkeypatch.setattr(handler, "_cognito", p)
    monkeypatch.setattr(handler, "_client_secret", lambda: SECRET)
    monkeypatch.setattr(handler, "_orders_client_secret", lambda: POOL_SECRET)
    monkeypatch.setattr(handler, "pool_config", lambda: dict(POOL))
    return p


@pytest.fixture
def pool(monkeypatch):
    return _wire(monkeypatch, _Pool())


def _form(**kw):
    return urllib.parse.urlencode(kw)


def _exchange_form(subject, **extra):
    return _form(grant_type=handler.TOKEN_EXCHANGE_GRANT, subject_token=subject,
                 subject_token_type=handler.JWT_TOKEN_TYPE, **extra)


def _event(body, secret=SECRET, client_id="exchange-client", method="POST", path="/token"):
    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    return {
        "requestContext": {"http": {"method": method, "path": path}},
        "headers": {"content-type": "application/x-www-form-urlencoded",
                    "authorization": f"Basic {auth}"},
        "body": body,
        "isBase64Encoded": False,
    }


def _body(resp):
    return json.loads(resp["body"])


# --- client authentication -----------------------------------------------------------
def test_missing_client_auth_is_401_with_a_challenge(pool):
    e = _event(_exchange_form(customer_token()))
    del e["headers"]["authorization"]
    r = handler.handle_token(e)
    assert r["statusCode"] == 401 and "WWW-Authenticate" in r["headers"]
    assert pool.calls == []


@pytest.mark.parametrize("kw", [{"secret": "wrong"}, {"client_id": "someone-else"},
                                {"client_id": POOL["client_id"], "secret": POOL_SECRET}])
def test_wrong_client_credentials_are_refused_uniformly(pool, kw):
    # Including the exchange pool's own app-client credentials: they are not the front door's.
    r = handler.handle_token(_event(_exchange_form(customer_token()), **kw))
    assert r["statusCode"] == 401 and _body(r) == {"error": "invalid_client"}
    assert pool.calls == []


# --- the request contract ------------------------------------------------------------
def test_wrong_grant_type(pool):
    r = handler.handle_token(_event(_form(grant_type="password", username="c-1000", password="x")))
    assert r["statusCode"] == 400 and _body(r)["error"] == "unsupported_grant_type"
    assert pool.calls == []


@pytest.mark.parametrize("extra, code", [
    ({"scope": "orders/admin"}, "invalid_scope"),
    ({"scope": "orders/read payments/write"}, "invalid_scope"),
    ({"audience": "payments-client-id"}, "invalid_target"),
    ({"resource": "https://payments"}, "invalid_target"),
    ({"actor_token": "x"}, "invalid_request"),
    ({"requested_token_type": "urn:ietf:params:oauth:token-type:id_token"}, "invalid_request"),
    ({"subject_token_type": "urn:ietf:params:oauth:token-type:saml2"}, "invalid_request"),
])
def test_request_parameters_cannot_widen_the_token(pool, extra, code):
    form = {"grant_type": handler.TOKEN_EXCHANGE_GRANT, "subject_token": customer_token(),
            "subject_token_type": handler.JWT_TOKEN_TYPE}
    form.update(extra)
    r = handler.handle_token(_event(_form(**form)))
    assert r["statusCode"] == 400 and _body(r)["error"] == code
    assert pool.calls == []


@pytest.mark.parametrize("extra", [
    {"username": "c-1001"}, {"sub": "attacker"}, {"customer_id": "c-1001"},
    {"aud": "payments"}, {"exp": "9999999999"}, {"actor_token_type": "urn:ietf:params:oauth:token-type:jwt"},
    {"client_id": "someone-else"},
])
def test_parameters_outside_the_contract_are_refused(pool, extra):
    # Claim-shaped or unknown parameters are refused outright, not ignored.
    form = {"grant_type": handler.TOKEN_EXCHANGE_GRANT, "subject_token": customer_token(),
            "subject_token_type": handler.JWT_TOKEN_TYPE}
    form.update(extra)
    r = handler.handle_token(_event(_form(**form)))
    assert r["statusCode"] == 400 and _body(r)["error"] == "invalid_request"
    assert pool.calls == []


def test_a_matching_client_id_in_the_body_is_tolerated(pool):
    r = handler.handle_token(_event(_exchange_form(customer_token(), client_id="exchange-client")))
    assert r["statusCode"] == 200


def test_the_configured_scope_and_audience_are_accepted(pool):
    r = handler.handle_token(_event(_exchange_form(customer_token(), scope="orders/read",
                                                   audience=POOL["client_id"])))
    assert r["statusCode"] == 200


def test_duplicate_parameters_are_malformed(pool):
    body = _exchange_form(customer_token()) + "&scope=orders/read&scope=orders/admin"
    r = handler.handle_token(_event(body))
    assert r["statusCode"] == 400 and _body(r)["error"] == "invalid_request"


# --- the subject token gate, before any Cognito call ---------------------------------
@pytest.mark.parametrize("subject", [
    customer_token(kid="unknown"), customer_token(token_use="id"),
    customer_token(client_id="someone-else"), "not.a.jwt",
])
def test_a_bad_subject_token_never_reaches_the_pool(pool, subject):
    r = handler.handle_token(_event(_exchange_form(subject)))
    assert r["statusCode"] == 400 and _body(r)["error"] == "invalid_grant"
    assert pool.calls == []


# --- what the pool is asked, and what comes back ------------------------------------
def test_a_successful_exchange_runs_the_custom_flow_as_the_service_user(pool):
    tok = customer_token(username="c-1000")
    r = handler.handle_token(_event(_exchange_form(tok)))
    assert r["statusCode"] == 200
    out = _body(r)
    assert out == {"access_token": MINTED, "issued_token_type": handler.ACCESS_TOKEN_TYPE,
                   "token_type": "Bearer", "expires_in": 300, "scope": "orders/read"}
    assert "id.tok.en" not in r["body"] and "refresh" not in r["body"]

    (name1, initiate), (name2, respond) = pool.calls
    assert (name1, name2) == ("initiate", "respond")
    assert initiate["UserPoolId"] == POOL["pool_id"] and initiate["ClientId"] == POOL["client_id"]
    assert initiate["AuthFlow"] == "CUSTOM_AUTH"
    assert initiate["AuthParameters"]["USERNAME"] == "orders-agent"
    assert respond["ChallengeName"] == "CUSTOM_CHALLENGE" and respond["Session"] == "session-1"
    assert respond["ChallengeResponses"]["ANSWER"] == tok
    assert respond["ClientMetadata"] == {"subject_token": tok, "grant": handler.TOKEN_EXCHANGE_GRANT}


def test_the_confidential_client_secret_hash_is_sent_on_both_calls(pool):
    handler.handle_token(_event(_exchange_form(customer_token())))
    expected = base64.b64encode(hmac.new(POOL_SECRET.encode(), b"orders-agent" + POOL["client_id"].encode(),
                                         hashlib.sha256).digest()).decode()
    (_, initiate), (_, respond) = pool.calls
    assert initiate["AuthParameters"]["SECRET_HASH"] == expected
    assert respond["ChallengeResponses"]["SECRET_HASH"] == expected


@pytest.mark.parametrize("fail", ["initiate", "respond", "no-token", "long", "long-token"])
def test_a_refused_flow_is_a_uniform_invalid_grant(monkeypatch, fail):
    # "long" and "long-token": a drifted client validity must not be handed out.
    _wire(monkeypatch, _Pool(fail=fail))
    r = handler.handle_token(_event(_exchange_form(customer_token())))
    assert r["statusCode"] == 400 and _body(r) == {"error": "invalid_grant",
                                                   "error_description": "subject token rejected"}


# --- discovery and routing --------------------------------------------------------------
def test_discovery_points_the_provider_at_this_token_endpoint_and_the_pools_keys():
    doc = _body(handler.handle_discovery({}))
    assert doc["token_endpoint"] == "https://exchange.example/token"
    assert doc["jwks_uri"].endswith("/us-east-1_exchange/.well-known/jwks.json")
    assert doc["grant_types_supported"] == [handler.TOKEN_EXCHANGE_GRANT]
    assert doc["token_endpoint_auth_methods_supported"] == ["client_secret_basic"]


def test_no_jwks_route_and_unknown_routes_are_404():
    assert handler.lambda_handler({"requestContext": {"http": {"method": "GET", "path": "/.well-known/jwks.json"}}},
                                  None)["statusCode"] == 404


def test_authorize_is_refused():
    assert _body(handler.handle_authorize({}))["error"] == "unsupported_response_type"


def test_an_unexpected_failure_is_a_bare_500(monkeypatch):
    monkeypatch.setitem(handler._ROUTES, ("GET", "/.well-known/openid-configuration"), lambda e: 1 / 0)
    r = handler.lambda_handler({"requestContext": {"http": {"method": "GET",
                                                            "path": "/.well-known/openid-configuration"}}}, None)
    assert r["statusCode"] == 500 and _body(r) == {"error": "server_error"}
