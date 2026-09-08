"""Contract tests for the identity-aware agent."""

import base64
import json
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer

import gateway
import main
import pytest
from main import Handler

calls = []
stopped = []
stored = []
listed = []

ORDERS = {
    "customer_id": "c-1000",
    "orders": [
        {"order_id": 1014, "status": "delivered"},
        {"order_id": 1275, "status": "shipped"},
    ],
}


class StubHandler(Handler):
    start = staticmethod(lambda interpreter, name: "session-123")
    run = staticmethod(
        lambda csv_text, session_id: calls.append((csv_text, session_id)) or "rows: 3"
    )
    stop = staticmethod(lambda interpreter, session_id: stopped.append(session_id))
    orders = staticmethod(
        lambda customer, token: listed.append((customer, token)) or json.dumps(ORDERS)
    )
    store = staticmethod(lambda actor, session, text: stored.append((actor, session, text)))
    history = staticmethod(lambda actor, session: [f"remembered for {actor}"])
    search = staticmethod(lambda actor, query: [f"a preference of {actor}"])


# find_order calls the module-level list_orders, so point that at the stub too.
main.list_orders = lambda customer, token: StubHandler.orders(customer, token)


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
    """The access token string the runtime would forward for this customer."""
    return token_for({"username": username, "sub": "x", "token_use": "access"})


def headers_for(username="c-1000"):
    headers = {"Content-Type": "application/json"}
    if username is not None:
        headers["Authorization"] = f"Bearer {bearer_for(username)}"
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


def test_a_token_without_token_use_is_refused(server_url):
    headers = headers_for()
    headers["Authorization"] = f"Bearer {token_for({'username': 'c-1000'})}"
    assert status_of(f"{server_url}/invocations", {"prompt": "my orders"}, headers) == 401


def test_the_body_is_read_before_an_early_401(server_url):
    """A large body with no token gets the JSON 401, not a reset."""
    headers = headers_for(username=None)
    big = {"prompt": "x" * 200_000}
    assert status_of(f"{server_url}/invocations", big, headers) == 401


def test_a_malformed_token_is_refused(server_url):
    headers = headers_for()
    headers["Authorization"] = "Bearer not.a.jwt"
    assert status_of(f"{server_url}/invocations", {"prompt": "my orders"}, headers) == 401


def test_my_orders_lists_the_callers_orders(server_url):
    listed.clear()
    status, body = post(f"{server_url}/invocations", {"prompt": "list my orders"})
    assert status == 200
    assert body == {"result": ORDERS}
    assert listed == [("c-1000", bearer_for("c-1000"))]


def test_the_customer_comes_from_the_token_not_the_body(server_url):
    stored.clear()
    post(f"{server_url}/invocations", {"prompt": "remember: I like DPD", "actor": "c-9999"})
    assert stored == [("c-1000", "default", "remember: I like DPD")]


def test_an_order_is_found_through_the_callers_own_orders(server_url):
    listed.clear()
    status, body = post(f"{server_url}/invocations", {"prompt": "where is order 1275?"})
    assert status == 200
    assert body == {"result": {"order_id": 1275, "status": "shipped"}}
    assert listed == [("c-1000", bearer_for("c-1000"))]


def test_someone_elses_order_is_not_on_your_account(server_url):
    status, body = post(f"{server_url}/invocations", {"prompt": "where is order 1090?"})
    assert status == 200
    assert body == {"result": {"error": "order 1090 is not on your account"}}


def test_recap_and_recall_are_scoped_to_the_caller(server_url):
    _, recap = post(f"{server_url}/invocations", {"prompt": "recap"})
    _, recall = post(f"{server_url}/invocations", {"prompt": "what do I like?"})
    assert recap == {"result": ["remembered for c-1000"]}
    assert recall == {"result": ["a preference of c-1000"]}


def test_csv_is_analysed_in_the_sandbox(server_url):
    status, body = post(f"{server_url}/invocations", {"csv": "a,b\n1,2\n"})
    assert status == 200
    assert body == {"result": "rows: 3"}
    assert calls[-1] == ("a,b\n1,2\n", "session-123")


def test_session_is_stopped_after_use(server_url):
    stopped.clear()
    post(f"{server_url}/invocations", {"csv": "a,b\n1,2\n"})
    assert stopped == ["session-123"]


def test_neither_csv_nor_prompt_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"actor": "andy"}) == 400


def test_non_string_csv_is_rejected(server_url):
    assert status_of(f"{server_url}/invocations", {"csv": ["a", "b"]}) == 400


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


def test_the_raw_bearer_token_is_extracted_for_relay():
    token = bearer_for("c-1000")
    assert main.bearer_from({"Authorization": f"Bearer {token}"}) == token
    assert main.bearer_from({"Authorization": "Basic abc"}) is None
    assert main.bearer_from({}) is None


def test_the_agent_relays_the_customers_own_token_to_the_gateway(server_url):
    """The gateway is called with the caller's token and their own id, so the
    policy engine has the caller it needs and the agent cannot forge another."""
    listed.clear()
    post(f"{server_url}/invocations", {"prompt": "list my orders"})
    customer, token = listed[-1]
    assert customer == "c-1000"
    assert token == bearer_for("c-1000")


def test_gateway_list_orders_forwards_the_id_and_token(monkeypatch):
    captured = {}

    async def fake_call(tool, arguments, customer_token):
        captured["tool"] = tool
        captured["arguments"] = arguments
        captured["token"] = customer_token
        return json.dumps({"customer_id": "c-1000", "orders": []})

    monkeypatch.setattr(gateway, "_call_tool", fake_call)
    gateway.list_orders("c-1000", "tok-123")
    assert captured == {
        "tool": "list_orders",
        "arguments": {"customer_id": "c-1000"},
        "token": "tok-123",
    }


class FakeInterpreter:
    """Records invoke calls and replays a canned stream for each."""

    def __init__(self, streams):
        self.streams = list(streams)
        self.invocations = []

    def invoke_code_interpreter(self, **kwargs):
        self.invocations.append(kwargs)
        return {"stream": self.streams.pop(0)}


def _text_event(text, is_error=False):
    return {
        "result": {"isError": is_error, "content": [{"type": "text", "text": text}]}
    }


@pytest.fixture
def fake(monkeypatch):
    fake = FakeInterpreter([])
    monkeypatch.setenv("CODE_INTERPRETER_ID", "ci-test")
    monkeypatch.setattr(main, "client", lambda: fake)
    return fake


def test_a_tool_error_raises_rather_than_returning_empty(fake):
    fake.streams = [[_text_event("NameError: pandas", is_error=True)]]
    with pytest.raises(RuntimeError, match="NameError"):
        main.execute_code("s1", "pandas.nope()")


def test_analyse_writes_then_executes_in_the_same_session(fake):
    fake.streams = [[_text_event("")], [_text_event("rows: 2")]]
    assert main.analyse("a,b\n1,2\n", "s9") == "rows: 2"
    assert [i["name"] for i in fake.invocations] == ["writeFiles", "executeCode"]
    assert {i["sessionId"] for i in fake.invocations} == {"s9"}
