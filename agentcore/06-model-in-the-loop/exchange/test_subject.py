"""The subject-token validator: the happy path, every negative case, and the bounded JWKS cache."""

import time

import jwt
import pytest
import subject
from conftest import customer_token, jwk_from_rsa

REAL_JWK_FOR_KID = subject._jwk_for_kid


def test_valid_token_returns_verified_claims():
    claims = subject.validate(customer_token())
    assert claims["username"] == "c-1000" and claims["sub"] == "u-1"


@pytest.mark.parametrize("token, why", [
    (customer_token(kid="unknown"), "unknown key"),
    (customer_token(iss="https://evil.example"), "wrong issuer"),
    (customer_token(token_use="id"), "id token"),
    (customer_token(client_id="someone-else"), "wrong client_id"),
    (customer_token(exp=int(time.time()) - 3600), "expired"),
    (customer_token(username=""), "empty username"),
    (customer_token(iat=int(time.time()) - 7200), "older than the max subject age"),
    ("not.a.jwt", "malformed"),
    (None, "not a string"),
    ("", "empty"),
])
def test_rejects_bad_tokens(token, why):
    with pytest.raises((ValueError, jwt.PyJWTError)):
        subject.validate(token)


def test_rejects_alg_none():
    unsigned = jwt.encode({"sub": "u-1", "iss": subject.COGNITO_ISSUER, "token_use": "access",
                           "username": "c-1000", "exp": int(time.time()) + 60,
                           "iat": int(time.time())},
                          key=None, algorithm="none", headers={"kid": "k1"})
    with pytest.raises((ValueError, jwt.PyJWTError)):
        subject.validate(unsigned)


def test_rejects_key_bearing_headers():
    from conftest import RSA
    tok = jwt.encode({"sub": "u-1", "iss": subject.COGNITO_ISSUER, "token_use": "access",
                      "username": "c-1000", "exp": int(time.time()) + 60,
                      "iat": int(time.time())},
                     RSA, algorithm="RS256", headers={"kid": "k1", "jku": "https://evil/jwks"})
    with pytest.raises(ValueError):
        subject.validate(tok)


# --- JWKS cache: last-known-good is bounded, not indefinite -------------------
def _jwks_cache_with(monkeypatch, keys, fetched_at, now, fetch):
    monkeypatch.setattr(subject, "_jwk_for_kid", REAL_JWK_FOR_KID)
    monkeypatch.setattr(subject, "_jwks_cache",
                        {"keys": keys, "at": fetched_at, "last_refresh": 0.0})
    monkeypatch.setattr(subject.time, "monotonic", lambda: now)
    monkeypatch.setattr(subject, "_fetch_jwks", fetch)


def _failing_fetch():
    raise OSError("jwks endpoint unreachable")


def test_refresh_failure_within_the_stale_bound_keeps_serving_the_cached_key(monkeypatch):
    fetched = 1000.0
    now = fetched + subject._JWKS_TTL + 60  # past fresh TTL, inside max stale
    _jwks_cache_with(monkeypatch, [jwk_from_rsa("k1")], fetched, now, _failing_fetch)
    assert subject._jwk_for_kid("k1")["kid"] == "k1"


def test_refresh_failure_past_the_stale_bound_refuses_every_kid(monkeypatch):
    fetched = 1000.0
    now = fetched + subject._JWKS_MAX_STALE + 1
    _jwks_cache_with(monkeypatch, [jwk_from_rsa("k1")], fetched, now, _failing_fetch)
    assert subject._jwk_for_kid("k1") is None
    with pytest.raises(ValueError):
        subject.validate(customer_token(kid="k1"))


def test_a_kid_removed_by_a_successful_refresh_is_no_longer_accepted(monkeypatch):
    fetched = 1000.0
    now = fetched + 10  # cache is fresh, but k1 is unknown so a refresh is tried
    _jwks_cache_with(monkeypatch, [jwk_from_rsa("k-old")], fetched, now,
                     lambda: [jwk_from_rsa("k-new")])
    assert subject._jwk_for_kid("k1") is None
    assert subject._jwk_for_kid("k-new")["kid"] == "k-new"
    assert subject._jwk_for_kid("k-old") is None  # replaced, not merged


def test_jwks_documents_are_validated_before_they_replace_the_cache(monkeypatch):
    import io
    import json

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def opener_for(doc):
        class _Opener:
            def open(self, req, timeout=0):
                return _Resp(json.dumps(doc).encode())
        return _Opener()

    monkeypatch.setattr(subject.urllib.request, "build_opener", lambda *a: opener_for(
        {"keys": [dict(jwk_from_rsa("k1"), d="private-material")]}))
    with pytest.raises(ValueError):
        subject._fetch_jwks()
    monkeypatch.setattr(subject.urllib.request, "build_opener", lambda *a: opener_for(
        {"keys": [jwk_from_rsa("k1"), jwk_from_rsa("k1")]}))
    with pytest.raises(ValueError):
        subject._fetch_jwks()  # duplicate kid
    monkeypatch.setattr(subject.urllib.request, "build_opener", lambda *a: opener_for(
        {"keys": [jwk_from_rsa("k1")]}))
    assert [k["kid"] for k in subject._fetch_jwks()] == ["k1"]
