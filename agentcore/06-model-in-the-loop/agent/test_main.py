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
from http.server import ThreadingHTTPServer

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
        or (f"answer for {customer}", [{"tool": "orders___list_orders", "input": {"customer_id": customer}}], [])
    )


@pytest.fixture(scope="module")
def server_url():
    server = ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def sid(label):
    """A session id of the runtime's minimum length, 33 characters."""
    return (label + "-").ljust(33, "0")


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
        f"{server_url}/invocations", {"prompt": "how much have I spent?"}, headers_for(session=sid("conv-1"))
    )
    assert status == 200
    assert body == {
        "result": "answer for c-1000",
        "trail": [{"tool": "orders___list_orders", "input": {"customer_id": "c-1000"}}],
        "unsupported_figures": [],
    }
    assert turns == [("how much have I spent?", "c-1000", sid("conv-1"), f"obo:{bearer_for('c-1000')}")]


def test_the_customer_comes_from_the_token_not_the_body(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "my orders", "customer": "c-1001", "actor": "c-1001", "session": sid("s1")})
    assert turns[-1][1] == "c-1000"


def test_the_model_is_given_the_minted_token_not_the_customers(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "my orders", "session": sid("s1")})
    token = turns[-1][3]
    assert token == f"obo:{bearer_for('c-1000')}"
    assert token != bearer_for("c-1000")


def test_the_runtime_session_header_names_the_conversation(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "hi", "session": sid("from-body")}, headers_for(session=sid("runtime-session-1")))
    assert turns[-1][2] == sid("runtime-session-1")


def test_the_body_session_is_used_outside_the_runtime(server_url):
    turns.clear()
    post(f"{server_url}/invocations", {"prompt": "hi", "session": sid("from-body")})
    assert turns[-1][2] == sid("from-body")


def test_a_request_with_no_session_is_rejected_not_defaulted(server_url):
    """Two clients of one customer must not silently share a conversation."""
    assert status_of(f"{server_url}/invocations", {"prompt": "hi"}) == 400


def test_a_malformed_session_id_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": "../c-1001"}) == 400
    assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": "x" * 200}) == 400


def test_a_session_id_shorter_than_the_runtimes_minimum_is_rejected(server_url):
    """The runtime requires 33 characters; a conversation named outside the
    runtime is held to the same rule, so short, guessable ids are refused."""
    assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": "s1"}) == 400
    assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": "x" * 32}) == 400
    assert post(f"{server_url}/invocations", {"prompt": "hi", "session": "x" * 33})[0] == 200


def test_turns_in_one_conversation_run_one_at_a_time(server_url):
    """The server answers requests concurrently; two turns for the same
    customer and session must not restore and append to one conversation at
    once, while turns for different sessions still overlap."""
    import time

    spans = []

    def slow(prompt, customer, session, token):
        started = time.monotonic()
        time.sleep(0.3)
        spans.append((session, started, time.monotonic()))
        return "ok", [], []

    original = StubHandler.respond
    StubHandler.respond = staticmethod(slow)
    try:
        for same in (True, False):
            spans.clear()
            sessions = [sid("same"), sid("same")] if same else [sid("one"), sid("two")]
            threads = [threading.Thread(target=post, args=(f"{server_url}/invocations", {"prompt": "hi", "session": x})) for x in sessions]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            (_, _, first_end), (_, second_start, _) = sorted(spans, key=lambda x: x[1])
            overlapped = second_start < first_end
            assert overlapped is (not same)
    finally:
        StubHandler.respond = original


def test_a_turns_entry_exists_exactly_while_a_turn_holds_or_waits_for_it():
    """The table cannot drop an entry from under a waiter, and holds one
    entry per conversation with a turn in flight, however many there are."""
    import time

    key = ("c-1000", sid("same"))
    seen = {}

    def first():
        with main.one_turn(*key):
            time.sleep(0.3)
            seen["while first holds"] = (main._turns[key][1], main._turns[key][0].locked())

    def second():
        with main.one_turn(*key):
            seen["while second holds"] = (main._turns[key][1], main._turns[key][0].locked())

    a = threading.Thread(target=first)
    a.start()
    time.sleep(0.05)
    b = threading.Thread(target=second)
    b.start()
    time.sleep(0.1)
    assert main._turns[key][1] == 2  # the waiter is counted, so the entry cannot be dropped
    a.join()
    b.join()
    assert seen["while first holds"] == (2, True)
    assert seen["while second holds"] == (1, True)
    assert key not in main._turns  # and nothing is kept once the turns are over

    def hold(n):
        with main.one_turn("c-1000", sid(f"many-{n}")):
            time.sleep(0.2)
            seen["in flight"] = max(seen.get("in flight", 0), len(main._turns))

    threads = [threading.Thread(target=hold, args=(n,)) for n in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert seen["in flight"] == 40 and main._turns == {}


def test_a_failing_turns_message_stays_out_of_the_log(server_url, capsys):
    """An exception's text can carry a response body, a token or the model's
    code; the log gets the class only."""
    def boom(prompt, customer, session, token):
        raise RuntimeError('Bearer eyJhbGciOi.eyJzdWIi.sig {"order_id": 1033} print(total)')

    original = StubHandler.respond
    StubHandler.respond = staticmethod(boom)
    try:
        assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": sid("s1")}) == 502
    finally:
        StubHandler.respond = original
    out = capsys.readouterr().out
    assert "turn failed for c-1000: RuntimeError" in out
    assert "eyJ" not in out and "1033" not in out and "print" not in out


def test_a_failing_turn_is_a_502_not_a_traceback(server_url):
    def boom(prompt, customer, session, token):
        raise RuntimeError("model unavailable")

    original = StubHandler.respond
    StubHandler.respond = staticmethod(boom)
    try:
        assert status_of(f"{server_url}/invocations", {"prompt": "hi", "session": sid("s1")}) == 502
    finally:
        StubHandler.respond = original


def test_a_budget_overrun_is_a_502_that_says_so(server_url):
    import trail

    def loops(prompt, customer, session, token):
        raise trail.BudgetExceeded("kept asking")

    original = StubHandler.respond
    StubHandler.respond = staticmethod(loops)
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            post(f"{server_url}/invocations", {"prompt": "hi", "session": sid("s1")})
        assert exc.value.code == 502
        assert "budget" in json.loads(exc.value.read())["error"]
    finally:
        StubHandler.respond = original


def test_an_oversized_prompt_is_refused_before_the_model(server_url):
    turns.clear()
    big = {"prompt": "x" * (main.MAX_PROMPT_CHARS + 1), "session": sid("s1")}
    assert status_of(f"{server_url}/invocations", big) == 400
    assert turns == []


def test_a_missing_prompt_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"csv": "a,b\n1,2\n", "session": sid("s1")}) == 400


def test_a_blank_prompt_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"prompt": "   ", "session": sid("s1")}) == 400


def test_a_non_string_prompt_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"prompt": ["list", "orders"], "session": sid("s1")}) == 400


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
