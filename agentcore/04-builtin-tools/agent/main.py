"""Agent for post 04: analyses data inside the AgentCore Code Interpreter.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). The agent
never parses the data itself, it writes the caller's CSV into a sandbox
session and runs pandas in there, so untrusted input is processed away
from the agent's own microVM. The code interpreter id arrives as an
environment variable set by Terraform on the runtime.
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from gateway import lookup_order
from memory import recall, recap, remember

PORT = 8080

# Anchored on the word "order" so a stray number in the prompt is ignored.
ORDER_RE = re.compile(r"\border\s*#?\s*(\d+)\b", re.IGNORECASE)

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


def _consume(response):
    """Drain a tool response stream, raising if the tool reported an error."""
    chunks = []
    for event in response.get("stream", []):
        result = event.get("result")
        if not result:
            continue
        text = "\n".join(
            item["text"]
            for item in result.get("content", [])
            if item.get("type") == "text"
        )
        if result.get("isError"):
            raise RuntimeError(text or "code interpreter tool failed")
        if text:
            chunks.append(text)
    return "\n".join(chunks).strip()


# The service exposes one data-plane call, invoke_code_interpreter, which
# takes a tool name and an arguments blob, the same shape as an MCP tools/call.
# That suits an agent forwarding model-chosen tools. This agent's code is
# fixed, so it wraps the tools it uses as functions instead. Callers get
# named parameters, and the stream is drained in exactly one place, so a
# failed tool cannot be mistaken for a successful empty one.
def _call(session_id, name, **arguments):
    response = client().invoke_code_interpreter(
        codeInterpreterIdentifier=os.environ["CODE_INTERPRETER_ID"],
        sessionId=session_id,
        name=name,
        arguments=arguments,
    )
    return _consume(response)


def write_files(session_id, path, text):
    return _call(session_id, "writeFiles", content=[{"path": path, "text": text}])


def execute_code(session_id, code, language="python"):
    return _call(session_id, "executeCode", code=code, language=language)


def analyse(csv_text, session_id):
    """Write the CSV into a sandbox session and describe it with pandas."""
    write_files(session_id, "data.csv", csv_text)
    return execute_code(session_id, ANALYSIS)


def stop_session(interpreter, session_id):
    client().stop_code_interpreter_session(
        codeInterpreterIdentifier=interpreter, sessionId=session_id
    )


def session_for(interpreter, name):
    resp = client().start_code_interpreter_session(
        codeInterpreterIdentifier=interpreter,
        name=name,
        sessionTimeoutSeconds=900,
    )
    return resp["sessionId"]


MAX_BODY_BYTES = 2 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    start = staticmethod(session_for)
    run = staticmethod(analyse)
    stop = staticmethod(stop_session)
    tool = staticmethod(lookup_order)
    store = staticmethod(remember)
    history = staticmethod(recap)
    search = staticmethod(recall)

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
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, {"error": "invalid Content-Length"})
            return
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send(413, {"error": "request body must be 1..2MB"})
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
        if isinstance(prompt, str) and prompt:
            self._handle_prompt(payload, prompt)
            return
        csv_text = payload.get("csv")
        if not isinstance(csv_text, str) or not csv_text:
            self._send(400, {"error": "csv or prompt is required"})
            return
        interpreter = os.environ.get("CODE_INTERPRETER_ID", "")
        session_id = None
        try:
            session_id = self.start(interpreter, "analysis")
            self._send(200, {"result": self.run(csv_text, session_id)})
        except Exception as exc:  # noqa: BLE001 — any sandbox failure becomes a 502
            print(f"code interpreter call failed: {exc}")
            self._send(502, {"error": "code interpreter request failed"})
        finally:
            if session_id is not None:
                try:
                    self.stop(interpreter, session_id)
                except Exception as exc:  # noqa: BLE001 — cleanup must not mask the result
                    print(f"failed to stop session {session_id}: {exc}")

    def _handle_prompt(self, payload, prompt):
        """Everything carried forward from posts 02 and 03."""
        actor = payload.get("actor", "anon")
        session = payload.get("session", "default")
        order = ORDER_RE.search(prompt)
        try:
            if prompt.lower().startswith("remember"):
                self.store(actor, session, prompt)
                self._send(200, {"result": "noted"})
            elif prompt.lower().startswith("recap"):
                self._send(200, {"result": self.history(actor, session)})
            elif order:
                self._send(200, {"result": self.tool(order.group(1))})
            else:
                self._send(200, {"result": self.search(actor, prompt)})
        except Exception as exc:  # noqa: BLE001 — any carried-forward failure is a 502
            print(f"prompt handling failed: {exc}")
            self._send(502, {"error": "request failed"})

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
