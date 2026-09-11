"""Shared test setup: environment, a test RSA key standing in for the customer pool, no network."""

import os
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

os.environ.update({
    "AWS_DEFAULT_REGION": "us-east-1",
    "COGNITO_ISSUER": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_customers",
    "COGNITO_JWKS_URL": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_customers/.well-known/jwks.json",
    "ALLOWED_CLIENT_IDS": "customers-client",
    "ISSUER_URL": "https://exchange.example",
    "EXCHANGE_JWKS_URL": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_exchange/.well-known/jwks.json",
    "EXCHANGE_CONFIG_PARAMETER": "/demos/agentcore/05/exchange",
    "ORDERS_CLIENT_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:111122223333:secret:orders-client",
    "ORDERS_SCOPE": "orders/read",
    "CLIENT_SECRET_ARN": "arn:aws:secretsmanager:us-east-1:111122223333:secret:test-abc",
    "EXCHANGE_CLIENT_ID": "exchange-client",
    "MAX_SUBJECT_AGE_SECONDS": "3600",
})

import subject

RSA = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64url_uint(value: int) -> str:
    import base64
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode()


def jwk_from_rsa(kid):
    nums = RSA.public_key().public_numbers()
    return {"kty": "RSA", "kid": kid, "use": "sig", "alg": "RS256",
            "n": _b64url_uint(nums.n), "e": _b64url_uint(nums.e)}


def customer_token(kid="k1", alg="RS256", **overrides):
    now = int(time.time())
    claims = {
        "sub": "u-1", "iss": subject.COGNITO_ISSUER, "client_id": "customers-client",
        "token_use": "access", "username": "c-1000", "iat": now, "exp": now + 3600,
    }
    claims.update(overrides)
    return jwt.encode(claims, RSA, algorithm=alg, headers={"kid": kid})


POOL = {"pool_id": "us-east-1_exchange", "client_id": "orders-client-id",
        "service_user": "orders-agent"}


@pytest.fixture(autouse=True)
def _pin_jwks(monkeypatch):
    # Pin the JWKS lookup to the test key; never touches the network.
    monkeypatch.setattr(subject, "_jwk_for_kid",
                        lambda kid: jwk_from_rsa("k1") if kid == "k1" else None)


@pytest.fixture(autouse=True)
def _pin_pool_config(monkeypatch):
    # The pool ids come from SSM at runtime; pin them here, never touch AWS.
    import triggers
    monkeypatch.setattr(triggers, "config", lambda: dict(POOL))
