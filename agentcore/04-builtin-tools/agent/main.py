"""Agent for post 04: analyses data inside the AgentCore Code Interpreter.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). The agent
never parses the data itself, it writes the caller's CSV into a sandbox
session and runs pandas in there, so untrusted input is processed away
from the agent's own microVM. The code interpreter id arrives as an
environment variable set by Terraform on the runtime.
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3

PORT = 8080

ANALYSIS = """
import pandas as pd

df = pd.read_csv("data.csv")
print(df.describe().to_string())
print()
print("rows:", len(df))
"""

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


def _text(response):
    chunks = []
    for event in response.get("stream", []):
        result = event.get("result", {})
        for item in result.get("content", []):
            if item.get("type") == "text":
                chunks.append(item["text"])
    return "\n".join(chunks).strip()


def analyse(csv_text, session_id):
    """Write the CSV into a sandbox session and describe it with pandas."""
    interpreter = os.environ["CODE_INTERPRETER_ID"]
    call = client().invoke_code_interpreter
    call(
        codeInterpreterIdentifier=interpreter,
        sessionId=session_id,
        name="writeFiles",
        arguments={"content": [{"path": "data.csv", "text": csv_text}]},
    )
    return _text(
        call(
            codeInterpreterIdentifier=interpreter,
            sessionId=session_id,
            name="executeCode",
            arguments={"language": "python", "code": ANALYSIS},
        )
    )


def session_for(interpreter, name):
    resp = client().start_code_interpreter_session(
        codeInterpreterIdentifier=interpreter,
        name=name,
        sessionTimeoutSeconds=900,
    )
    return resp["sessionId"]


class Handler(BaseHTTPRequestHandler):
    start = staticmethod(session_for)
    run = staticmethod(analyse)

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
        csv_text = payload.get("csv")
        if not isinstance(csv_text, str) or not csv_text:
            self._send(400, {"error": "csv must be a non-empty string"})
            return
        try:
            session_id = self.start(os.environ.get("CODE_INTERPRETER_ID", ""), "analysis")
            self._send(200, {"result": self.run(csv_text, session_id)})
        except Exception as exc:  # noqa: BLE001 — any sandbox failure becomes a 502
            print(f"code interpreter call failed: {exc}")
            self._send(502, {"error": "code interpreter request failed"})

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
