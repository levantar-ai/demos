"""Agent for post 03: remembers things about a user with AgentCore Memory.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). The agent
stores conversation turns as memory events (short-term) and answers
questions from the user-preference records the memory service extracts
from them (long-term, across sessions). Memory id arrives as an
environment variable set by Terraform on the runtime.
"""

import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from gateway import lookup_order

PORT = 8080

# Anchored on the word "order" so a stray number in the prompt is ignored.
ORDER_RE = re.compile(r"\border\s*#?\s*(\d+)\b", re.IGNORECASE)

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


def recap(actor, session):
    resp = client().list_events(
        memoryId=os.environ["MEMORY_ID"],
        actorId=actor,
        sessionId=session,
        maxResults=20,
    )
    return [
        p["conversational"]["content"]["text"]
        for e in resp.get("events", [])
        for p in e.get("payload", [])
        if "conversational" in p
    ]


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
    history = staticmethod(recap)
    search = staticmethod(recall)
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
        actor = payload.get("actor")
        session = payload.get("session")
        prompt = payload.get("prompt")
        if not all(isinstance(v, str) and v for v in (actor, session, prompt)):
            self._send(400, {"error": "actor, session and prompt are required strings"})
            return
        try:
            order = ORDER_RE.search(prompt)
            if prompt.lower().startswith("remember"):
                self.store(actor, session, prompt)
                self._send(200, {"result": "noted"})
            elif prompt.lower().startswith("recap"):
                self._send(200, {"result": self.history(actor, session)})
            elif order:
                # Carried forward from post 02, the tool still works here.
                self._send(200, {"result": self.tool(order.group(1))})
            else:
                self._send(200, {"result": self.search(actor, prompt)})
        except Exception as exc:  # noqa: BLE001 — any memory failure becomes a 502
            print(f"memory call failed: {exc}")
            self._send(502, {"error": "memory service request failed"})

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
