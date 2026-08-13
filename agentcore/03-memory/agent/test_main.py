"""Contract tests for the memory agent."""

import json
import threading
import urllib.request
from http.server import HTTPServer

import pytest
from main import Handler

stored = []


class StubHandler(Handler):
    store = staticmethod(lambda actor, session, text: stored.append((actor, session, text)))
    history = staticmethod(lambda actor, session: ["remember: I prefer DPD"])
    tool = staticmethod(lambda order_id: f'order {order_id}: {{"status": "shipped"}}')
    search = staticmethod(lambda actor, query: ["Prefers DPD deliveries"])


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


def test_remember_stores_an_event(server_url):
    status, body = post(
        f"{server_url}/invocations",
        {"actor": "andy", "session": "s1", "prompt": "remember: I prefer DPD"},
    )
    assert status == 200
    assert body == {"result": "noted"}
    assert stored == [("andy", "s1", "remember: I prefer DPD")]


def test_question_returns_records(server_url):
    status, body = post(
        f"{server_url}/invocations",
        {"actor": "andy", "session": "s2", "prompt": "which carrier do I prefer?"},
    )
    assert status == 200
    assert body == {"result": ["Prefers DPD deliveries"]}


def test_recap_returns_session_events(server_url):
    status, body = post(
        f"{server_url}/invocations",
        {"actor": "andy", "session": "s1", "prompt": "recap"},
    )
    assert status == 200
    assert body == {"result": ["remember: I prefer DPD"]}


def test_missing_session_is_rejected(server_url):
    req = urllib.request.Request(
        f"{server_url}/invocations",
        data=json.dumps({"actor": "andy", "prompt": "remember: x"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_missing_actor_is_rejected(server_url):
    req = urllib.request.Request(
        f"{server_url}/invocations",
        data=json.dumps({"prompt": "hello"}).encode(),
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


def test_order_prompt_uses_the_gateway_tool(server_url):
    status, body = post(
        f"{server_url}/invocations",
        {"actor": "andy", "session": "s1", "prompt": "where is order 42?"},
    )
    assert status == 200
    assert body == {"result": 'order 42: {"status": "shipped"}'}
