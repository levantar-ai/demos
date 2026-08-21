"""Brightwell's order agent, post 04: billing reconciliation in a sandbox.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). A customer
posts the charges export from their account. The agent fetches that
customer's orders through the gateway (post 02), writes both files into a
Code Interpreter session and joins them there, so the customer's upload is
parsed away from the agent's own microVM and its credentials. What it finds
is noted in memory (post 03) so a later session can recap it.
"""

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from gateway import list_orders, lookup_order
from memory import recall, recap, remember

PORT = 8080

# Anchored on the word "order" so a stray number in the prompt is ignored.
ORDER_RE = re.compile(r"\border\s*#?\s*(\d+)\b", re.IGNORECASE)

# Runs inside the sandbox. charges.csv is the customer's upload, untrusted.
# orders.json is what the tool returned for their account. Joining on
# order_id finds charges with no order behind them, orders charged more than
# once, and amounts that do not match the order total.
RECONCILE = """
import json
import pandas as pd

charges = pd.read_csv("charges.csv")
orders = pd.DataFrame(json.load(open("orders.json"))["orders"])

paid = charges.groupby("order_id")["amount"].agg(paid="sum", times="count").reset_index()
joined = orders.merge(paid, on="order_id", how="outer", indicator=True)

findings = []
for _, r in joined.iterrows():
    oid = int(r["order_id"])
    if r["_merge"] == "right_only":
        findings.append(f"order {oid}: charged {r['paid']:.2f} but there is no such order on this account")
        continue
    if r["_merge"] == "left_only":
        continue
    # Work in pence. Several captures that add up to the total are a split
    # payment, not a fault, so only the difference decides anything.
    diff = round(r["paid"] * 100) - round(r["total"] * 100)
    if diff == 0:
        continue
    taken = f"charged {int(r['times'])} times totalling {r['paid']:.2f}" if r["times"] > 1 else f"charged {r['paid']:.2f}"
    if diff > 0:
        findings.append(f"order {oid}: {taken} against a total of {r['total']:.2f}, refund due {diff / 100:.2f}")
    else:
        findings.append(f"order {oid}: {taken} against a total of {r['total']:.2f}, {-diff / 100:.2f} outstanding")

print(f"{len(orders)} orders on the account, {len(charges)} charges in the export")
if findings:
    print(f"{len(findings)} discrepancies")
    for f in findings:
        print("-", f)
else:
    print("no discrepancies, every charge matches an order")
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


def analyse(charges_csv, orders_json, session_id):
    """Write both files into the sandbox session and reconcile them there."""
    write_files(session_id, "charges.csv", charges_csv)
    write_files(session_id, "orders.json", orders_json)
    return execute_code(session_id, RECONCILE)


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
    orders = staticmethod(list_orders)
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
        actor = payload.get("actor")
        if not isinstance(actor, str) or not actor:
            self._send(
                400,
                {
                    "error": "actor is required with csv, it is the customer whose orders to reconcile"
                },
            )
            return
        session = payload.get("session")
        self._reconcile(actor, session, csv_text)

    def _reconcile(self, actor, session, charges_csv):
        """Fetch the customer's orders, then join them against the upload in a sandbox."""
        interpreter = os.environ.get("CODE_INTERPRETER_ID", "")
        session_id = None
        try:
            orders_json = self.orders(actor)
            session_id = self.start(interpreter, "reconcile")
            report = self.run(charges_csv, orders_json, session_id)
        except Exception as exc:  # noqa: BLE001 — gateway or sandbox failure is a 502
            print(f"reconciliation failed: {exc}")
            self._send(502, {"error": "reconciliation request failed"})
            return
        finally:
            if session_id is not None:
                try:
                    self.stop(interpreter, session_id)
                except Exception as exc:  # noqa: BLE001 — cleanup must not mask the result
                    print(f"failed to stop session {session_id}: {exc}")
        # Best effort, the answer is already computed. The whole report goes in,
        # it is a few lines, so a later session's recap has the findings.
        if isinstance(session, str) and session:
            try:
                self.store(actor, session, f"billing query: {report or 'no output'}")
            except Exception as exc:  # noqa: BLE001
                print(f"memory write failed: {exc}")
        self._send(200, {"result": report})

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
