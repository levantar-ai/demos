"""Agent for post 02: answers order questions by calling an MCP tool
through AgentCore Gateway.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). Tool
calls go through the MCP Python SDK over a bearer token from Cognito.
The client secret is read from Secrets Manager with the runtime
execution role, never passed in as configuration. Endpoints arrive as
environment variables set by Terraform.
"""

import asyncio
import base64
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = 8080
MAX_BODY_BYTES = 64 * 1024

# The gateway namespaces tool names as <target>___<tool>, three underscores.
TOOL_NAME = "orders___lookup_order"

# Tokens are reused until shortly before they expire.
EXPIRY_MARGIN = 60
_token = {"value": None, "expires_at": 0.0}
_token_lock = threading.Lock()


def _client_credentials():
    secret = boto3.client("secretsmanager").get_secret_value(
        SecretId=os.environ["CLIENT_SECRET_ARN"]
    )
    credentials = json.loads(secret["SecretString"])
    return credentials["client_id"], credentials["client_secret"]


def access_token():
    # Double-checked under the lock: the server is threaded, so without it a
    # burst of requests around expiry would each fetch the secret and mint a
    # token rather than sharing one.
    if _token["value"] and time.time() < _token["expires_at"]:
        return _token["value"]

    with _token_lock:
        if _token["value"] and time.time() < _token["expires_at"]:
            return _token["value"]

        client_id, client_secret = _client_credentials()
        form = urllib.parse.urlencode(
            {"grant_type": "client_credentials", "scope": os.environ["TOKEN_SCOPE"]}
        ).encode()
        # Credentials go in the Authorization header, not the form body, which
        # keeps them out of anything that logs request bodies.
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        request = urllib.request.Request(
            os.environ["TOKEN_URL"],
            data=form,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {basic}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())

        _token["value"] = payload["access_token"]
        _token["expires_at"] = time.time() + payload["expires_in"] - EXPIRY_MARGIN
        return _token["value"]


async def _call_tool(order_id):
    headers = {"Authorization": f"Bearer {access_token()}"}
    async with (
        streamablehttp_client(os.environ["GATEWAY_URL"], headers=headers) as (read, write, _),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        result = await session.call_tool(TOOL_NAME, {"order_id": order_id})
        return _result_text(result)


def _result_text(result):
    """Pull the text out of an MCP tool result, refusing anything unexpected.

    A tool that sets isError still arrives as a well-formed response, so
    without this check a failure reads as an answer.
    """
    if result.isError:
        raise RuntimeError(f"tool reported an error: {result.content}")
    for item in result.content or []:
        if getattr(item, "type", None) == "text":
            return item.text
    raise RuntimeError(f"tool returned no text content: {result.content}")


def lookup_order(order_id):
    return asyncio.run(_call_tool(order_id))


class Handler(BaseHTTPRequestHandler):
    tool = staticmethod(lookup_order)

    def do_GET(self):
        if self.path == "/ping":
            self._send(200, {"status": "Healthy"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/invocations":
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return
        if length > MAX_BODY_BYTES:
            self._send(413, {"error": "payload too large"})
            return
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "payload must be a JSON object"})
            return
        prompt = payload.get("prompt")
        if not isinstance(prompt, str):
            self._send(400, {"error": "prompt must be a string"})
            return
        # Anchored on the word "order" so "in 2 days, where is order 42?"
        # looks up 42 rather than 2.
        match = re.search(r"\border\s*#?\s*(\d+)\b", prompt, re.IGNORECASE)
        if not match:
            self._send(200, {"result": "no order id found in the prompt"})
            return
        order_id = match.group(1)
        try:
            order = self.tool(order_id)
        except Exception as exc:  # noqa: BLE001 — any tool failure becomes a 502
            print(f"gateway call failed: {exc}")
            self._send(502, {"error": "gateway request failed"})
            return
        self._send(200, {"result": f"order {order_id}: {order}"})

    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


if __name__ == "__main__":
    print(f"agent listening on :{PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
