"""Contract tests for the handler with the model stubbed out.

The HTTP contract, the caller check and the exchange are what this file
covers. The model's behaviour is not testable without Bedrock; what the
model is told and given is tested in test_model.py, and what it did on the
deployed stack is in artifacts/README.md.
"""

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import main
import pytest
from main import Handler

turns = []


class StubHandler(Handler):
    # The on-behalf-of exchange is stubbed: it stands for AgentCore Identity
    # brokering a token the gateway accepts from the customer's inbound JWT.
    exchange = staticmethod(lambda inbound: f"obo:{inbound}")
    respond = staticmethod(
        lambda prompt, customer, session, token: turns.append((prompt, customer, session, token))
        or (f"answer for {customer}", [{"tool": "orders___list_orders", "input": {"customer_id": customer}}])
    )


@pytest.fixture(scope="module")
def server_url():
    server = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


def token_for(claims):
    """An unsigned JWT shaped like Cognito's. The runtime is what verifies
    signatures, so the agent only ever sees the payload."""
    return f"{_b64({'alg': 'RS256'})}.{_b64(claims)}.signature"


def bearer_for(username):
    return token_for({"username": username, "sub": "x", "token_use": "access"})


def headers_for(username="c-1000", session=None):
    headers = {"Content-Type": "application/json"}
    if username is not None:
        headers["Authorization"] = f"Bearer {bearer_for(username)}"
    if session is not None:
        headers[main.SESSION_HEADER] = session
    return headers


def post(url, body, headers=None):
    req = urllib.request.Request(
        url,
        data=body if isinstance(body, bytes) else json.dumps(body).encode(),
        headers=headers or headers_for(),
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def status_of(url, body, headers=None):
    with pytest.raises(urllib.error.HTTPError) as exc:
        post(url, body, headers)
    return exc.value.code


def test_ping_reports_healthy(server_url):
    with urllib.request.urlopen(f"{server_url}/ping") as resp:
        assert resp.status == 200
        assert json.loads(resp.read()) == {"status": "Healthy"}


def test_a_request_without_a_bearer_token_is_refused(server_url):
    headers = headers_for(username=None)
    assert status_of(f"{server_url}/invocations", {"prompt": "my orders"}, headers) == 401


def test_a_token_without_a_username_claim_is_refused(server_url):
    headers = headers_for()
    headers["Authorization"] = f"Bearer {token_for({'sub': 'x', 'token_use': 'access'})}"
    assert status_of(f"{server_url}/invocations", {"prompt": "my orders"}, headers) == 401


def test_an_id_token_is_refused(server_url):
    headers = headers_for()
    claims = {"cognito:username": "c-1000", "username": "c-1000", "token_use": "id"}
    headers["Authorization"] = f"Bearer {token_for(claims)}"
    assert status_of(f"{server_url}/invocations", {"prompt": "my orders"}, headers) == 401


def test_a_malformed_token_is_refused(server_url):
    headers = headers_for()
    headers["Authorization"] = "Bearer not.a.jwt"
    assert status_of(f"{server_url}/invocations", {"prompt": "my orders"}, headers) == 401


def test_the_body_is_read_before_an_early_401(server_url):
    """A large body with no token gets the JSON 401, not a reset."""
    headers = headers_for(username=None)
    assert status_of(f"{server_url}/invocations", {"prompt": "x" * 200_000}, headers) == 401


def test_a_prompt_goes_to_the_model_as_the_verified_customer(server_url):
    turns.clear()
    status, body = post(
        f"{server_url}/invocations", {"prompt": "how much have I spent?"}, headers_for(session="conv-1")
    )
    assert status == 200
    assert body == {
        "result": "answer for c-1000",
        "trail": [{"tool": "orders___list_orders", "input": {"customer_id": "c-1000"}}],
    }
    assert turns == [("how much have I spent?", "c-1000", "conv-1", f"obo:{bearer_for('c-1000')}")]


def test_the_customer_comes_from_the_token_not_the_body(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "my orders", "customer": "c-1001", "actor": "c-1001", "session": "s1"})
    assert turns[-1][1] == "c-1000"


def test_the_model_is_given_the_minted_token_not_the_customers(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "my orders", "session": "s1"})
    token = turns[-1][3]
    assert token == f"obo:{bearer_for('c-1000')}"
    assert token != bearer_for("c-1000")


def test_the_runtime_session_header_names_the_conversation(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "hi", "session": "from-body"}, headers_for(session="runtime-session-1"))
    assert turns[-1][2] == "runtime-session-1"


def test_the_body_session_is_used_outside_the_runtime(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "hi", "session": "from-body"})
    assert turns[-1][2] == "from-body"


def test_a_request_with_no_session_is_rejected_not_defaulted(server_url):
    """Two clients of one customer must not silently share a conversation."""
    assert status_of(f"{server_url}/invocations", {"prompt": "hi"}) == 400


def test_a_malformed_session_id_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": "../c-1001"}) == 400
    assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": "x" * 200}) == 400


def test_a_failing_turn_is_a_502_not_a_traceback(server_url):
    def boom(prompt, customer, session, token):
        raise RuntimeError("model unavailable")

    original = StubHandler.respond
    StubHandler.respond = staticmethod(boom)
    try:
        assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": "s1"}) == 502
    finally:
        StubHandler.respond = original


def test_a_missing_prompt_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"csv": "a,b\n1,2\n", "session": "s1"}) == 400


def test_a_blank_prompt_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"prompt": "   ", "session": "s1"}) == 400


def test_a_non_string_prompt_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"prompt": ["list", "orders"], "session": "s1"}) == 400


def test_non_object_json_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", b'["not", "an", "object"]') == 400


def test_invalid_json_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", b"{not json") == 400


def test_claims_are_decoded_without_verification():
    claims = {"username": "c-1001", "exp": 1, "token_use": "access"}
    headers = {"Authorization": f"Bearer {token_for(claims)}"}
    assert main.customer_from(headers) == "c-1001"
    assert main.customer_from({"Authorization": "Basic abc"}) is None
    assert main.customer_from({}) is None


def test_the_raw_bearer_token_is_extracted_for_the_exchange():
    token = bearer_for("c-1000")
    assert main.bearer_from({"Authorization": f"Bearer {token}"}) == token
    assert main.bearer_from({"Authorization": "Basic abc"}) is None
    assert main.bearer_from({}) is None
