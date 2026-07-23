"""Contract tests for the AgentCore Runtime HTTP interface."""

import json
import threading
import urllib.request
from http.server import HTTPServer

import pytest

from main import Handler


@pytest.fixture(scope="module")
def server_url():
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def get(url):
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read())


def post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read())


def test_ping_reports_healthy(server_url):
    status, body = get(f"{server_url}/ping")
    assert status == 200
    assert body == {"status": "healthy"}


def test_invocations_echoes_prompt(server_url):
    status, body = post(f"{server_url}/invocations", {"prompt": "hello"})
    assert status == 200
    assert body == {"result": "echo: hello"}


def test_invocations_handles_empty_payload(server_url):
    status, body = post(f"{server_url}/invocations", {})
    assert status == 200
    assert body == {"result": "echo: "}


def test_invalid_json_is_rejected(server_url):
    req = urllib.request.Request(
        f"{server_url}/invocations",
        data=b"not json",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 400


def test_unknown_path_is_404(server_url):
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{server_url}/nope")
    assert exc.value.code == 404
