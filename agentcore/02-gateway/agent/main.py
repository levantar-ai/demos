"""Agent for post 02: answers order questions by calling an MCP tool
through AgentCore Gateway.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping), standard
library only. The gateway endpoint, token endpoint and client credentials
arrive as environment variables set by Terraform on the runtime.
"""

import json
import os
import re
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = 8080


def get_token():
    data = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": os.environ["COGNITO_CLIENT_ID"],
            "client_secret": os.environ["COGNITO_CLIENT_SECRET"],
            "scope": os.environ["TOOL_SCOPE"],
        }
    ).encode()
    req = urllib.request.Request(
        os.environ["COGNITO_TOKEN_URL"],
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def mcp_request(method, params, token):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode()
    req = urllib.request.Request(
        os.environ["GATEWAY_URL"],
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def lookup_order(order_id):
    token = get_token()
    tools = mcp_request("tools/list", {}, token)["result"]["tools"]
    tool_name = next(t["name"] for t in tools if t["name"].endswith("___lookup_order"))
    result = mcp_request(
        "tools/call",
        {"name": tool_name, "arguments": {"order_id": order_id}},
        token,
    )
    return result["result"]["content"][0]["text"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ping":
            self._send(200, {"status": "healthy"})
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
        prompt = payload.get("prompt", "")
        match = re.search(r"\d+", prompt)
        if not match:
            self._send(200, {"result": "no order id found in the prompt"})
            return
        order_id = match.group()
        try:
            order = self.tool(order_id)
        except Exception as exc:  # noqa: BLE001 — any tool failure becomes a 502
            self._send(502, {"error": f"gateway call failed: {exc}"})
            return
        self._send(200, {"result": f"order {order_id}: {order}"})

    # seam for tests; the real implementation calls the gateway
    tool = staticmethod(lookup_order)

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
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
