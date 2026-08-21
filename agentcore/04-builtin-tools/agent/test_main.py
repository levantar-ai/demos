"""Contract tests for the code interpreter agent."""

import json
import threading
import urllib.request
from http.server import HTTPServer

import main
import pytest
from main import Handler

calls = []
stopped = []
stored = []


class StubHandler(Handler):
    start = staticmethod(lambda interpreter, name: "session-123")
    run = staticmethod(
        lambda charges_csv, orders_json, session_id: (
            calls.append((charges_csv, orders_json, session_id)) or "1 discrepancies"
        )
    )
    orders = staticmethod(lambda actor: f'{{"customer_id": "{actor}", "orders": []}}')
    stop = staticmethod(lambda interpreter, session_id: stopped.append(session_id))
    tool = staticmethod(lambda order_id: f'order {order_id}: {{"status": "shipped"}}')
    store = staticmethod(
        lambda actor, session, text: stored.append((actor, session, text))
    )
    history = staticmethod(lambda actor, session: ["remembered"])
    search = staticmethod(lambda actor, query: ["a preference"])


@pytest.fixture(scope="module")
def server_url():
    server = HTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def test_ping_reports_healthy(server_url):
    with urllib.request.urlopen(f"{server_url}/ping") as resp:
        assert resp.status == 200
        assert json.loads(resp.read()) == {"status": "Healthy"}


def test_csv_is_reconciled_against_the_customers_orders(server_url):
    status, body = post(
        f"{server_url}/invocations",
        {"actor": "c-1007", "csv": "order_id,charged_at,amount\n"},
    )
    assert status == 200
    assert body == {"result": "1 discrepancies"}
    assert calls[-1] == (
        "order_id,charged_at,amount\n",
        '{"customer_id": "c-1007", "orders": []}',
        "session-123",
    )


def test_csv_without_actor_is_rejected(server_url):
    req = urllib.request.Request(
        f"{server_url}/invocations",
        data=json.dumps({"csv": "order_id,charged_at,amount\n"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_session_is_stopped_after_use(server_url):
    stopped.clear()
    post(
        f"{server_url}/invocations",
        {"actor": "c-1007", "csv": "order_id,charged_at,amount\n"},
    )
    assert stopped == ["session-123"]


def test_reconciliation_is_noted_in_memory_when_a_session_is_given(server_url):
    stored.clear()
    post(
        f"{server_url}/invocations",
        {
            "actor": "c-1007",
            "session": "billing-query",
            "csv": "order_id,charged_at,amount\n",
        },
    )
    assert stored == [("c-1007", "billing-query", "billing query: 1 discrepancies")]


def test_neither_csv_nor_prompt_is_rejected(server_url):
    req = urllib.request.Request(
        f"{server_url}/invocations",
        data=json.dumps({"actor": "andy"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_order_prompt_uses_the_gateway_tool(server_url):
    status, body = post(f"{server_url}/invocations", {"prompt": "where is order 42?"})
    assert status == 200
    assert body == {"result": 'order 42: {"status": "shipped"}'}


def test_remember_prompt_uses_memory(server_url):
    status, body = post(f"{server_url}/invocations", {"prompt": "remember: I like DPD"})
    assert status == 200
    assert body == {"result": "noted"}


def test_non_string_csv_is_rejected(server_url):
    req = urllib.request.Request(
        f"{server_url}/invocations",
        data=json.dumps({"csv": ["a", "b"]}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_non_object_json_is_rejected(server_url):
    req = urllib.request.Request(
        f"{server_url}/invocations",
        data=b'["not", "an", "object"]',
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


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


def test_write_files_sends_the_tool_name_and_arguments(fake):
    fake.streams = [[_text_event("ok")]]
    assert main.write_files("s1", "data.csv", "a,b\n") == "ok"
    assert fake.invocations == [
        {
            "codeInterpreterIdentifier": "ci-test",
            "sessionId": "s1",
            "name": "writeFiles",
            "arguments": {"content": [{"path": "data.csv", "text": "a,b\n"}]},
        }
    ]


def test_execute_code_defaults_to_python(fake):
    fake.streams = [[_text_event("rows: 3")]]
    assert main.execute_code("s1", "print(1)") == "rows: 3"
    assert fake.invocations[0]["name"] == "executeCode"
    assert fake.invocations[0]["arguments"] == {
        "code": "print(1)",
        "language": "python",
    }


def test_a_tool_error_raises_rather_than_returning_empty(fake):
    fake.streams = [[_text_event("NameError: pandas", is_error=True)]]
    with pytest.raises(RuntimeError, match="NameError"):
        main.execute_code("s1", "pandas.nope()")


def test_analyse_writes_both_files_then_executes_in_the_same_session(fake):
    fake.streams = [
        [_text_event("")],
        [_text_event("")],
        [_text_event("2 discrepancies")],
    ]
    assert (
        main.analyse("order_id,charged_at,amount\n", '{"orders": []}', "s9")
        == "2 discrepancies"
    )
    assert [i["name"] for i in fake.invocations] == [
        "writeFiles",
        "writeFiles",
        "executeCode",
    ]
    assert [i["arguments"]["content"][0]["path"] for i in fake.invocations[:2]] == [
        "charges.csv",
        "orders.json",
    ]
    assert {i["sessionId"] for i in fake.invocations} == {"s9"}
