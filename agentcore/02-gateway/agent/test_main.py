"""Contract tests for the gateway-calling agent."""

import json
import threading
import urllib.request
from http.server import HTTPServer

import pytest
from main import Handler


class StubHandler(Handler):
    tool = staticmethod(lambda order_id: json.dumps({"status": "shipped"}))


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


def test_order_question_calls_tool(server_url):
    status, body = post(
        f"{server_url}/invocations", {"prompt": "where is order 42?"}
    )
    assert status == 200
    assert body == {"result": 'order 42: {"status": "shipped"}'}


def test_prompt_without_order_id(server_url):
    status, body = post(f"{server_url}/invocations", {"prompt": "hello"})
    assert status == 200
    assert body == {"result": "no order id found in the prompt"}


def test_tool_failure_returns_502(server_url):
    class FailingHandler(StubHandler):
        tool = staticmethod(lambda order_id: (_ for _ in ()).throw(RuntimeError("boom")))

    server = HTTPServer(("127.0.0.1", 0), FailingHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/invocations",
            data=json.dumps({"prompt": "order 7"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 502
    finally:
        server.shutdown()
