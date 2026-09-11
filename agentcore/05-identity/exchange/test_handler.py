"""Unit tests for the token-exchange service.

These prove the security-critical parts without AWS: the subject-token validator
(all the negative JWT cases the review demanded) and the DER->JOSE signature
conversion. KMS signing and Secrets Manager are stubbed. Run: python3 -m pytest.
"""

import base64
import json
import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "COGNITO_ISSUER": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test",
    "COGNITO_JWKS_URL": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test/.well-known/jwks.json",
    "ALLOWED_CLIENT_IDS": "customers-client",
    "ISSUER_URL": "https://exchange.example",
    "ORDERS_AUDIENCE": "brightwell-orders",
    "ORDERS_SCOPE": "orders/read",
    "KMS_KEY_ID": "arn:aws:kms:us-east-1:111122223333:key/abcd-1234",
    "CLIENT_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:111122223333:secret:test-abc",
    "EXCHANGE_CLIENT_ID": "exchange-client",
    "MAX_TTL_SECONDS": "300",
    "MIN_REMAINING_SECONDS": "30",
    "MAX_SUBJECT_AGE_SECONDS": "3600",
})

import handler


def _b64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return handler._b64url(value.to_bytes(length, "big"))


_RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_from_rsa(kid):
    nums = _RSA.public_key().public_numbers()
    return {
        "kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
        "n": _b64url_uint(nums.n), "e": _b64url_uint(nums.e),
    }


def _cognito_token(kid="k1", alg="RS256", **overrides):
    now = int(time.time())
    claims = {
        "sub": "u-1", "iss": handler.COGNITO_ISSUER, "client_id": "customers-client",
        "token_use": "access", "username": "c-1000", "iat": now, "exp": now + 3600,
    }
    claims.update(overrides)
    return jwt.encode(claims, _RSA, algorithm=alg, headers={"kid": kid})


@pytest.fixture(autouse=True)
def _pin_jwks(monkeypatch):
    # Pin the JWKS lookup to our test key; never touches the network.
    monkeypatch.setattr(handler, "_jwk_for_kid",
                        lambda kid: _jwk_from_rsa("k1") if kid == "k1" else None)


# --- validator: happy path + every negative case -----------------------------
def test_valid_token_returns_verified_claims():
    claims = handler.validate_subject_token(_cognito_token())
    assert claims["username"] == "c-1000" and claims["sub"] == "u-1"


@pytest.mark.parametrize("token, why", [
    (_cognito_token(kid="unknown"), "unknown key"),
    (_cognito_token(iss="https://evil.example"), "wrong issuer"),
    (_cognito_token(token_use="id"), "id token"),
    (_cognito_token(client_id="someone-else"), "wrong client_id"),
    (_cognito_token(exp=int(time.time()) - 3600), "expired"),
    (_cognito_token(username=""), "empty username"),
    ("not.a.jwt", "malformed"),
])
def test_rejects_bad_tokens(token, why):
    with pytest.raises((ValueError, jwt.PyJWTError)):
        handler.validate_subject_token(token)


def test_rejects_alg_none():
    unsigned = jwt.encode({"sub": "u-1", "iss": handler.COGNITO_ISSUER,
                           "token_use": "access", "username": "c-1000",
                           "exp": int(time.time()) + 60, "iat": int(time.time())},
                          key=None, algorithm="none", headers={"kid": "k1"})
    with pytest.raises((ValueError, jwt.PyJWTError)):
        handler.validate_subject_token(unsigned)


def test_rejects_disallowed_header():
    tok = jwt.encode({"sub": "u-1", "iss": handler.COGNITO_ISSUER, "token_use": "access",
                      "username": "c-1000", "exp": int(time.time()) + 60,
                      "iat": int(time.time())},
                     _RSA, algorithm="RS256", headers={"kid": "k1", "jku": "https://evil/jwks"})
    with pytest.raises(ValueError):
        handler.validate_subject_token(tok)


# --- DER -> JOSE signature conversion ----------------------------------------
def test_der_to_jose_is_fixed_width_64_bytes():
    key = ec.generate_private_key(ec.SECP256R1())
    der = encode_dss_signature(1, 2)  # tiny r,s -> must still be left-padded to 32 bytes each
    jose = handler._der_to_jose(der)
    assert len(jose) == 64
    assert jose[:32] == (1).to_bytes(32, "big")
    assert jose[32:] == (2).to_bytes(32, "big")
    del key


def test_signed_jwt_verifies_against_the_published_jwk(monkeypatch):
    # Sign with a local EC key standing in for KMS, then verify via the JWK the
    # service would publish -> proves header/payload/signature round-trip.
    ec_key = ec.generate_private_key(ec.SECP256R1())

    def fake_get_public_key(KeyId):
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        return {"PublicKey": ec_key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo)}

    def fake_sign(KeyId, Message, MessageType, SigningAlgorithm):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import utils as au
        sig = ec_key.sign(Message, ec.ECDSA(au.Prehashed(hashes.SHA256())))
        return {"Signature": sig, "KeyId": handler.KMS_KEY_ARN}

    monkeypatch.setattr(handler._kms, "get_public_key", fake_get_public_key)
    monkeypatch.setattr(handler._kms, "sign", fake_sign)
    handler._signing["kid"] = None  # force reload

    token = handler.sign_jwt({"iss": handler.ISSUER_URL, "aud": "brightwell-orders",
                              "username": "c-1000", "exp": int(time.time()) + 300})
    jwk = handler._signing["jwk"]
    pub = jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk))
    decoded = jwt.decode(token, key=pub, algorithms=["ES256"], audience="brightwell-orders")
    assert decoded["username"] == "c-1000"
    assert jwt.get_unverified_header(token)["kid"] == jwk["kid"]


# --- /token request handling --------------------------------------------------
def _form(**kw):
    import urllib.parse
    return urllib.parse.urlencode(kw)


def test_token_requires_client_auth(monkeypatch):
    monkeypatch.setattr(handler, "_client_secret", lambda: "shared-secret")
    event = {"headers": {"content-type": "application/x-www-form-urlencoded"},
             "body": _form(grant_type=handler.TOKEN_EXCHANGE_GRANT)}
    assert handler.handle_token(event)["statusCode"] == 401


def test_token_rejects_wrong_grant(monkeypatch):
    monkeypatch.setattr(handler, "_client_secret", lambda: "shared-secret")
    good = base64.b64encode(b"exchange-client:shared-secret").decode()
    event = {"headers": {"authorization": f"Basic {good}",
                         "content-type": "application/x-www-form-urlencoded"},
             "body": _form(grant_type="password")}
    resp = handler.handle_token(event)
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["error"] == "unsupported_grant_type"


# --- a successful exchange binds claims to the verified subject only ----------
def _stub_kms(monkeypatch, key_id=None):
    ec_key = ec.generate_private_key(ec.SECP256R1())

    def fake_get_public_key(KeyId):
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        return {"PublicKey": ec_key.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo)}

    def fake_sign(KeyId, Message, MessageType, SigningAlgorithm):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import utils as au
        sig = ec_key.sign(Message, ec.ECDSA(au.Prehashed(hashes.SHA256())))
        return {"Signature": sig, "KeyId": key_id or handler.KMS_KEY_ARN}

    monkeypatch.setattr(handler._kms, "get_public_key", fake_get_public_key)
    monkeypatch.setattr(handler._kms, "sign", fake_sign)
    handler._signing["kid"] = None
    return ec_key


def _good_event(body, secret="shared-secret"):
    auth = base64.b64encode(f"exchange-client:{secret}".encode()).decode()
    return {"headers": {"authorization": f"Basic {auth}",
                        "content-type": "application/x-www-form-urlencoded"},
            "body": body}


def _exchange_form(subject, **extra):
    return _form(grant_type=handler.TOKEN_EXCHANGE_GRANT, subject_token=subject,
                 subject_token_type=handler.JWT_TOKEN_TYPE, **extra)


def test_successful_exchange_copies_only_the_verified_subject(monkeypatch):
    monkeypatch.setattr(handler, "_client_secret", lambda: "shared-secret")
    _stub_kms(monkeypatch)
    resp = handler.handle_token(_good_event(_exchange_form(_cognito_token(username="c-1000",
                                                                          sub="u-1"))))
    assert resp["statusCode"] == 200
    out = json.loads(resp["body"])
    assert out["issued_token_type"] == handler.ACCESS_TOKEN_TYPE
    jwk = handler._signing["jwk"]
    claims = jwt.decode(out["access_token"], key=jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk)),
                        algorithms=["ES256"], audience="brightwell-orders")
    assert claims["username"] == "c-1000" and claims["sub"] == "u-1"
    assert claims["iss"] == handler.ISSUER_URL and claims["scope"] == "orders/read"
    assert claims["act"] == {"client_id": "exchange-client"}
    assert 0 < claims["exp"] - claims["iat"] <= 300


def test_identity_claims_cannot_be_chosen_by_request_parameters(monkeypatch):
    # The anti-impersonation property: username and sub come from the verified
    # subject token and from nowhere else. Identity-looking parameters in the
    # form are ignored, not honoured.
    monkeypatch.setattr(handler, "_client_secret", lambda: "shared-secret")
    _stub_kms(monkeypatch)
    form = _exchange_form(_cognito_token(username="c-1000", sub="u-1"),
                          username="c-1001", sub="attacker", client_id="other",
                          aud="payments", exp="9999999999")
    resp = handler.handle_token(_good_event(form))
    assert resp["statusCode"] == 200
    out = json.loads(resp["body"])
    jwk = handler._signing["jwk"]
    claims = jwt.decode(out["access_token"], key=jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk)),
                        algorithms=["ES256"], audience="brightwell-orders")
    assert claims["username"] == "c-1000" and claims["sub"] == "u-1"
    assert claims["aud"] == "brightwell-orders" and claims["act"] == {"client_id": "exchange-client"}
    assert claims["exp"] - claims["iat"] <= 300


def test_output_lifetime_is_capped_by_the_subjects_remaining_life(monkeypatch):
    monkeypatch.setattr(handler, "_client_secret", lambda: "shared-secret")
    _stub_kms(monkeypatch)
    now = int(time.time())
    short = _cognito_token(exp=now + 120, iat=now)  # 2 minutes left, less than MAX_TTL
    resp = handler.handle_token(_good_event(_exchange_form(short)))
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["expires_in"] <= 120


def test_sign_refuses_an_unexpected_kms_key_id(monkeypatch):
    _stub_kms(monkeypatch, key_id="arn:aws:kms:us-east-1:111122223333:key/some-other-key")
    with pytest.raises(RuntimeError):
        handler.sign_jwt({"iss": handler.ISSUER_URL, "exp": int(time.time()) + 60})


@pytest.mark.parametrize("extra, code", [
    ({"scope": "orders/admin"}, "invalid_scope"),
    ({"audience": "payments"}, "invalid_target"),
    ({"resource": "https://payments"}, "invalid_target"),
    ({"actor_token": "x"}, "invalid_request"),
    ({"requested_token_type": "urn:ietf:params:oauth:token-type:id_token"}, "invalid_request"),
])
def test_request_parameters_cannot_widen_the_token(monkeypatch, extra, code):
    monkeypatch.setattr(handler, "_client_secret", lambda: "shared-secret")
    resp = handler.handle_token(_good_event(_exchange_form(_cognito_token(), **extra)))
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["error"] == code


def test_wrong_client_secret_is_refused_uniformly(monkeypatch):
    monkeypatch.setattr(handler, "_client_secret", lambda: "shared-secret")
    resp = handler.handle_token(_good_event(_exchange_form(_cognito_token()), secret="wrong"))
    assert resp["statusCode"] == 401
    assert json.loads(resp["body"]) == {"error": "invalid_client"}
    assert "WWW-Authenticate" in resp["headers"]


# --- JWKS cache: last-known-good is bounded, not indefinite -------------------
def _jwks_cache_with(monkeypatch, keys, fetched_at, now, fetch):
    # Use the real _jwk_for_kid (the autouse fixture pins it); seed the cache
    # as if the document was fetched at `fetched_at` and the clock is `now`.
    monkeypatch.setattr(handler, "_jwk_for_kid", _REAL_JWK_FOR_KID)
    monkeypatch.setattr(handler, "_jwks_cache",
                        {"keys": keys, "at": fetched_at, "last_refresh": 0.0})
    monkeypatch.setattr(handler.time, "monotonic", lambda: now)
    monkeypatch.setattr(handler, "_fetch_jwks", fetch)


_REAL_JWK_FOR_KID = handler._jwk_for_kid


def _failing_fetch():
    raise OSError("jwks endpoint unreachable")


def test_refresh_failure_within_the_stale_bound_keeps_serving_the_cached_key(monkeypatch):
    fetched = 1000.0
    now = fetched + handler._JWKS_TTL + 60  # past fresh TTL, inside max stale
    _jwks_cache_with(monkeypatch, [_jwk_from_rsa("k1")], fetched, now, _failing_fetch)
    assert handler._jwk_for_kid("k1")["kid"] == "k1"


def test_refresh_failure_past_the_stale_bound_refuses_every_kid(monkeypatch):
    fetched = 1000.0
    now = fetched + handler._JWKS_MAX_STALE + 1
    _jwks_cache_with(monkeypatch, [_jwk_from_rsa("k1")], fetched, now, _failing_fetch)
    assert handler._jwk_for_kid("k1") is None
    # and the validator therefore rejects a token signed with that key
    with pytest.raises(ValueError):
        handler.validate_subject_token(_cognito_token(kid="k1"))


def test_a_kid_removed_by_a_successful_refresh_is_no_longer_accepted(monkeypatch):
    fetched = 1000.0
    now = fetched + 10  # cache is fresh, but k1 is unknown so a refresh is tried
    _jwks_cache_with(monkeypatch, [_jwk_from_rsa("k-old")], fetched, now,
                     lambda: [_jwk_from_rsa("k-new")])
    assert handler._jwk_for_kid("k1") is None
    assert handler._jwk_for_kid("k-new")["kid"] == "k-new"
    assert handler._jwk_for_kid("k-old") is None  # replaced, not merged
