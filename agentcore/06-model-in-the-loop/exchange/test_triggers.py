"""The exchange pool's triggers: the state machine, the verification, the claims, and every fail-closed branch."""

import copy

import pytest
import triggers
from conftest import customer_token

BASE = {
    "version": "1",
    "userPoolId": "us-east-1_exchange",
    "userName": "orders-agent",
    "callerContext": {"clientId": "orders-client-id", "awsSdkVersion": "x"},
    "request": {},
    "response": {},
}


def ev(**request):
    e = copy.deepcopy(BASE)
    e["request"].update(request)
    return e


# --- the guard every trigger applies ---------------------------------------------
@pytest.mark.parametrize("mutate", [
    lambda e: e.update(userPoolId="us-east-1_other"),
    lambda e: e["callerContext"].update(clientId="some-other-client"),
    lambda e: e.update(userName="c-1000"),
    lambda e: e.pop("callerContext"),
])
@pytest.mark.parametrize("trigger", [triggers.define, triggers.create, triggers.verify, triggers.pretoken])
def test_every_trigger_refuses_the_wrong_pool_client_or_user(trigger, mutate):
    e = ev(session=[], challengeAnswer=customer_token())
    mutate(e)
    with pytest.raises(triggers.Refused):
        trigger(e, None)


# --- define: exactly one challenge, answered once ---------------------------------
def test_define_issues_the_challenge_on_a_fresh_session():
    r = triggers.define(ev(session=[]), None)["response"]
    assert r == {"issueTokens": False, "failAuthentication": False,
                 "challengeName": "CUSTOM_CHALLENGE"}


def test_define_issues_tokens_after_one_correct_answer():
    r = triggers.define(ev(session=[{"challengeName": "CUSTOM_CHALLENGE",
                                     "challengeResult": True}]), None)["response"]
    assert r == {"issueTokens": True, "failAuthentication": False}


@pytest.mark.parametrize("session", [
    [{"challengeName": "CUSTOM_CHALLENGE", "challengeResult": False}],
    [{"challengeName": "CUSTOM_CHALLENGE", "challengeResult": "true"}],  # not a bool
    [{"challengeName": "PASSWORD_VERIFIER", "challengeResult": True}],
    [{"challengeName": "CUSTOM_CHALLENGE", "challengeResult": True}] * 2,  # a second round
])
def test_define_fails_anything_else(session):
    r = triggers.define(ev(session=session), None)["response"]
    assert r["failAuthentication"] is True and r["issueTokens"] is False
    assert "challengeName" not in r


def test_define_fails_an_unknown_user_without_a_challenge():
    r = triggers.define(ev(session=[], userNotFound=True), None)["response"]
    assert r["failAuthentication"] is True and "challengeName" not in r


# --- create ---------------------------------------------------------------------------
def test_create_asks_for_the_subject_token_and_holds_no_secret():
    r = triggers.create(ev(), None)["response"]
    assert r["publicChallengeParameters"] == {"type": triggers.TOKEN_EXCHANGE_GRANT}
    assert r["privateChallengeParameters"] == {}


# --- verify --------------------------------------------------------------------------
def _verify_event(answer, metadata_token=None):
    return ev(challengeAnswer=answer,
              clientMetadata={"subject_token": metadata_token if metadata_token is not None else answer,
                              "grant": triggers.TOKEN_EXCHANGE_GRANT})


def test_verify_accepts_a_valid_customer_token():
    assert triggers.verify(_verify_event(customer_token()), None)["response"] == {"answerCorrect": True}


@pytest.mark.parametrize("answer", [
    customer_token(kid="unknown"),
    customer_token(token_use="id"),
    customer_token(client_id="someone-else"),
    customer_token(exp=int(__import__("time").time()) + 10),  # inside leeway, but about to expire
    "garbage", "", None,
])
def test_verify_rejects_anything_that_is_not_a_valid_customer_token(answer):
    assert triggers.verify(_verify_event(answer), None)["response"] == {"answerCorrect": False}


def test_verify_binds_the_answer_to_the_metadata_copy_pretoken_will_read():
    a, b = customer_token(username="c-1000"), customer_token(username="c-1001")
    assert triggers.verify(_verify_event(a, metadata_token=b), None)["response"] == {"answerCorrect": False}
    e = ev(challengeAnswer=a)  # no metadata at all
    assert triggers.verify(e, None)["response"] == {"answerCorrect": False}


# --- pretoken: the claims, and every way to not get them ---------------------------
def _pretoken_event(token=None, **over):
    e = ev(clientMetadata={"subject_token": token if token is not None else customer_token(),
                           "grant": triggers.TOKEN_EXCHANGE_GRANT},
           userAttributes={"sub": "service-sub"}, scopes=["aws.cognito.signin.user.admin"])
    e.update(version="2", triggerSource="TokenGeneration_Authentication")
    e.update(over)
    return e


def test_pretoken_writes_the_customer_and_the_audience_from_the_verified_token():
    out = triggers.pretoken(_pretoken_event(customer_token(username="c-1000", sub="u-1")), None)
    access = out["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]
    assert access["claimsToAddOrOverride"] == {
        "aud": "orders-client-id", "customer_id": "c-1000", "customer_sub": "u-1",
    }
    assert access["scopesToAdd"] == ["orders/read"]
    assert access["scopesToSuppress"] == ["aws.cognito.signin.user.admin"]


def test_pretoken_takes_the_customer_from_the_token_not_from_metadata():
    e = _pretoken_event(customer_token(username="c-1000"))
    e["request"]["clientMetadata"]["customer_id"] = "c-1001"  # caller-supplied noise
    e["request"]["userAttributes"]["custom:customer_id"] = "c-1001"
    out = triggers.pretoken(e, None)
    claims = out["response"]["claimsAndScopeOverrideDetails"]["accessTokenGeneration"]["claimsToAddOrOverride"]
    assert claims["customer_id"] == "c-1000"


@pytest.mark.parametrize("mutate", [
    lambda e: e.update(triggerSource="TokenGeneration_RefreshTokens"),
    lambda e: e.update(triggerSource="TokenGeneration_HostedAuth"),
    lambda e: e.update(triggerSource="TokenGeneration_NewPasswordChallenge"),
    lambda e: e.update(version="1"),
    lambda e: e["request"].pop("clientMetadata"),
    lambda e: e["request"]["clientMetadata"].pop("grant"),
    lambda e: e["request"]["clientMetadata"].update(grant="client_credentials"),
    lambda e: e["request"]["clientMetadata"].pop("subject_token"),
    lambda e: e["request"]["clientMetadata"].update(subject_token=customer_token(kid="unknown")),
    lambda e: e["request"]["clientMetadata"].update(subject_token=customer_token(token_use="id")),
    lambda e: e["request"]["clientMetadata"].update(subject_token="garbage"),
    lambda e: e["request"]["clientMetadata"].update(
        subject_token=customer_token(exp=int(__import__("time").time()) + 10)),
])
def test_pretoken_refuses_every_other_path_to_a_token(mutate):
    e = _pretoken_event()
    mutate(e)
    with pytest.raises(Exception):  # noqa: B017 — Refused or a validation error; either fails the flow
        triggers.pretoken(e, None)
