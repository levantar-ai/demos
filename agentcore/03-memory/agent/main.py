"""Agent for post 03: remembers things about a user with AgentCore Memory.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). The agent
stores conversation turns as memory events (short-term) and answers
questions from the user-preference records the memory service extracts
from them (long-term, across sessions). Memory id arrives as an
environment variable set by Terraform on the runtime.
"""

import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3

PORT = 8080

_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


def remember(actor, session, text):
    client().create_event(
        memoryId=os.environ["MEMORY_ID"],
        actorId=actor,
        sessionId=session,
        eventTimestamp=datetime.now(timezone.utc),
        payload=[{"conversational": {"content": {"text": text}, "role": "USER"}}],
    )


def recall(actor, query):
    resp = client().retrieve_memory_records(
        memoryId=os.environ["MEMORY_ID"],
        namespace=f"/users/{actor}",
        searchCriteria={"searchQuery": query},
        maxResults=5,
    )
    return [r["content"]["text"] for r in resp.get("memoryRecordSummaries", [])]


class Handler(BaseHTTPRequestHandler):
    store = staticmethod(remember)
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
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid JSON"})
            return
        actor = payload.get("actor", "")
        session = payload.get("session", "")
        prompt = payload.get("prompt", "")
        if not actor or not prompt:
            self._send(400, {"error": "actor and prompt are required"})
            return
        try:
            if prompt.lower().startswith("remember"):
                self.store(actor, session, prompt)
                self._send(200, {"result": "noted"})
            else:
                records = self.search(actor, prompt)
                self._send(200, {"result": records})
        except Exception as exc:  # noqa: BLE001 — any memory failure becomes a 502
            self._send(502, {"error": f"memory call failed: {exc}"})

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
