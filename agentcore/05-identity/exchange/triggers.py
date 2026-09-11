"""The exchange pool's Lambda triggers: where the token is actually verified and minted.

This is the AWS sample's arrangement (aws-samples/sample-cognito-oauth2-token-
exchange). The exchange front door (handler.py) cannot mint a token. It can
only start a CUSTOM_AUTH flow in the exchange pool as the agent's service user
and hand the customer's Cognito token over as the challenge answer. These four
triggers decide whether Cognito issues anything, and what it says:

  define    the custom-auth state machine: one challenge, then tokens or fail
  create    the challenge itself, which asks for the subject token
  verify    verifies the answer, the customer's token, against the customer
            pool, and requires it to equal the copy in clientMetadata, which
            is what pretoken will read: the two are bound by that equality
  pretoken  verifies the clientMetadata copy again (Cognito passes that field
            through unvalidated), then writes the claims the gateway and Cedar
            use: aud (the session's app client, the one value Cognito allows),
            customer_id and customer_sub from the verified token, the
            orders/read scope; and suppresses aws.cognito.signin.user.admin

Which pool, app client and user the triggers serve is read from one SSM
parameter written after the pool exists, because the pool references the
triggers and so the triggers cannot be given the pool's ids at deploy time.

Every trigger fails closed: any event not from this pool, this client and
this user, or any token generation that is not the completed exchange flow,
raises and Cognito fails the authentication. Nothing about the token is logged.
"""

import json
import os
import time

import boto3
import subject

CONFIG_PARAMETER = os.environ["EXCHANGE_CONFIG_PARAMETER"]
ORDERS_SCOPE = os.environ["ORDERS_SCOPE"]

TOKEN_EXCHANGE_GRANT = "urn:ietf:params:oauth:grant-type:token-exchange"
CUSTOM_CHALLENGE = "CUSTOM_CHALLENGE"
AUTHENTICATION = "TokenGeneration_Authentication"

_ssm = boto3.client("ssm")
_config_cache = {"value": None, "at": 0.0}
_CONFIG_TTL = 300


class Refused(Exception):
    """Raised to make Cognito fail the flow. The message reaches the caller as Cognito's error, so keep it generic."""


def config() -> dict:
    now = time.monotonic()
    if _config_cache["value"] is None or now - _config_cache["at"] > _CONFIG_TTL:
        raw = _ssm.get_parameter(Name=CONFIG_PARAMETER)["Parameter"]["Value"]
        cfg = json.loads(raw)
        for key in ("pool_id", "client_id", "service_user"):
            if not isinstance(cfg.get(key), str) or not cfg[key]:
                raise RuntimeError("exchange configuration incomplete")
        _config_cache["value"] = cfg
        _config_cache["at"] = now
    return _config_cache["value"]


def _guard(event) -> dict:
    """Only this pool, this app client and this user may be in an exchange flow."""
    cfg = config()
    if event.get("userPoolId") != cfg["pool_id"]:
        raise Refused("wrong pool")
    if (event.get("callerContext") or {}).get("clientId") != cfg["client_id"]:
        raise Refused("wrong client")
    if event.get("userName") != cfg["service_user"]:
        raise Refused("wrong user")
    return event.get("request") or {}


def define(event, _context):
    request = _guard(event)
    response = {"issueTokens": False, "failAuthentication": True}
    session = request.get("session") or []
    if request.get("userNotFound"):
        pass  # no challenge for a user that does not exist
    elif not session:
        response = {"issueTokens": False, "failAuthentication": False,
                    "challengeName": CUSTOM_CHALLENGE}
    elif (len(session) == 1 and session[0].get("challengeName") == CUSTOM_CHALLENGE
          and session[0].get("challengeResult") is True):
        response = {"issueTokens": True, "failAuthentication": False}
    event["response"] = response  # exactly one challenge, answered once, or fail
    return event


def create(event, _context):
    _guard(event)
    event["response"] = {
        "publicChallengeParameters": {"type": TOKEN_EXCHANGE_GRANT},
        "privateChallengeParameters": {},
        "challengeMetadata": "TOKEN_EXCHANGE",
    }
    return event


def verify(event, _context):
    request = _guard(event)
    answer = request.get("challengeAnswer")
    metadata = request.get("clientMetadata") or {}
    ok = False
    try:
        # The answer must be the very token pretoken will read from
        # clientMetadata, so a caller cannot answer with one customer's token
        # and have another customer's claims minted.
        if isinstance(answer, str) and answer and answer == metadata.get("subject_token"):
            subject.validate(answer)
            ok = True
    except Exception:  # noqa: BLE001 — any failure is a wrong answer; say nothing more
        ok = False
    event["response"] = {"answerCorrect": ok}
    return event


def pretoken(event, _context):
    request = _guard(event)
    # No single check here proves the custom flow ran. The combination does:
    # the client allows only CUSTOM_AUTH, define issues exactly one challenge,
    # verify bound the answer to the metadata copy, and the metadata marker
    # and token below are required and validated again. A refresh reaches
    # this trigger with TokenGeneration_RefreshTokens and no metadata, and is
    # refused here (confirmed live: Cognito processed a refresh attempt on the
    # custom-auth-only client, and this raise is what stopped it).
    if event.get("version") != "2" or event.get("triggerSource") != AUTHENTICATION:
        raise Refused("not an exchange")
    metadata = request.get("clientMetadata") or {}
    if metadata.get("grant") != TOKEN_EXCHANGE_GRANT:
        raise Refused("not an exchange")
    # clientMetadata is caller-supplied and Cognito does not validate it, so
    # the token is verified again here, by the trigger that decides the claims.
    claims = subject.validate(metadata.get("subject_token"))
    client_id = event["callerContext"]["clientId"]
    event["response"] = {
        "claimsAndScopeOverrideDetails": {
            "accessTokenGeneration": {
                "claimsToAddOrOverride": {
                    "aud": client_id,  # Cognito permits aud only as the session's client id
                    "customer_id": claims["username"],
                    "customer_sub": claims["sub"],
                },
                "scopesToAdd": [ORDERS_SCOPE],
                "scopesToSuppress": ["aws.cognito.signin.user.admin"],
            },
            "idTokenGeneration": {"claimsToSuppress": []},
        },
    }
    return event
