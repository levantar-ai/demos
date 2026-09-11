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
