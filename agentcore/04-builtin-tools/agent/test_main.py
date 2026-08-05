"""Contract tests for the code interpreter agent."""

import json
import threading
import urllib.request
from http.server import HTTPServer

import pytest
from main import Handler

calls = []
stopped = []


class StubHandler(Handler):
    start = staticmethod(lambda interpreter, name: "session-123")
    run = staticmethod(
        lambda csv_text, session_id: calls.append((csv_text, session_id)) or "rows: 3"
    )
    stop = staticmethod(lambda interpreter, session_id: stopped.append(session_id))
    tool = staticmethod(lambda order_id: f'order {order_id}: {{"status": "shipped"}}')
    store = staticmethod(lambda actor, session, text: None)
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
