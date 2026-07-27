"""Agent for post 02: answers order questions by calling an MCP tool
through AgentCore Gateway.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). Gateway
calls are signed with SigV4 using the runtime execution role, so there
are no credentials to configure anywhere. The gateway endpoint arrives as
an environment variable set by Terraform on the runtime.
"""

import json
import os
import re
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import botocore.session
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

PORT = 8080

_session = None


def credentials():
    global _session
    if _session is None:
        _session = botocore.session.Session()
    return _session.get_credentials()


def mcp_request(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    request = AWSRequest(
        method="POST",
        url=os.environ["GATEWAY_URL"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    SigV4Auth(credentials(), "bedrock-agentcore", os.environ["AWS_REGION"]).add_auth(request)
    req = urllib.request.Request(
        request.url, data=body.encode(), headers=dict(request.headers), method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def lookup_order(order_id):
    tool_name = "orders___lookup_order"
    tools = {t["name"] for t in mcp_request("tools/list", {})["result"]["tools"]}
    if tool_name not in tools:
        raise RuntimeError(f"required tool not found: {tool_name}")
    result = mcp_request(
        "tools/call",
        {"name": tool_name, "arguments": {"order_id": order_id}},
    )
    return result["result"]["content"][0]["text"]


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
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "payload must be a JSON object"})
            return
        prompt = payload.get("prompt", "")
        match = re.search(r"\d+", prompt)
        if not match:
            self._send(200, {"result": "no order id found in the prompt"})
            return
        order_id = match.group()
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
