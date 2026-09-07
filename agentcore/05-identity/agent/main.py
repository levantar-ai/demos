"""Brightwell's order agent, post 05: knowing who is calling.

Runtime HTTP contract as post 01 (POST /invocations, GET /ping). The runtime
now validates a customer's bearer token before a request reaches this
handler and forwards the Authorization header, so the caller's identity
comes from claims the runtime has verified rather than from the request
body. The runtime also hands over a workload access token for the request,
which is what the agent presents to AgentCore Identity when it needs a
gateway token. There is still no model in this agent, the routing below is
code. Post 06 is where a model is handed these tools, acting as the
customer this post identifies.
"""

import base64
import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import boto3
from gateway import list_orders
from memory import recall, recap, remember

PORT = 8080

# Anchored on the word "order" so a stray number in the prompt is ignored.
ORDER_RE = re.compile(r"\border\s*#?\s*(\d+)\b", re.IGNORECASE)
MY_ORDERS_RE = re.compile(r"\bmy orders\b", re.IGNORECASE)

# Headers the runtime adds. The workload access token identifies this agent
# to AgentCore Identity for the duration of the request; the SDK accepts
# either spelling, so this does too.
WORKLOAD_TOKEN_HEADERS = ("X-Amz-Bedrock-AgentCore-Identity-WAT", "WorkloadAccessToken")

# Runs inside the sandbox, carried forward from post 04.
ANALYSIS = """
import pandas as pd

df = pd.read_csv("data.csv")
print(df.describe().to_string())
print()
print("rows:", len(df))
"""


def claims_from(headers):
    """The bearer token's claims, or None when there is no usable token.

    The runtime has already checked the signature, issuer, expiry and client
    against the pool's discovery document before forwarding the header, so
    this decodes the payload and does not verify it again.
    """
    auth = headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = auth[len("Bearer "):].split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError):
        return None
    return claims if isinstance(claims, dict) else None


def customer_from(headers):
    """The calling customer. Brightwell's customer ids are the pool's usernames."""
    username = (claims_from(headers) or {}).get("username")
    return username if isinstance(username, str) and username else None


def workload_token_from(headers):
    for name in WORKLOAD_TOKEN_HEADERS:
        value = headers.get(name)
        if value:
            return value
    return None


def find_order(order_id, customer, workload_token):
    """One of the customer's own orders, so an id from someone else's
    account is not found rather than looked up."""
    listed = json.loads(list_orders(customer, workload_token))
    for order in listed.get("orders", []):
        if str(order.get("order_id")) == str(order_id):
            return order
    return {"error": f"order {order_id} is not on your account"}


_client = None


def client():
    global _client
    if _client is None:
        _client = boto3.client("bedrock-agentcore")
    return _client


def _consume(response):
    """Drain a tool response stream, then raise if the tool reported an error."""
    chunks, error = [], None
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
            error = error or text or "code interpreter tool failed"
            continue
        if text:
            chunks.append(text)
    if error is not None:
        raise RuntimeError(error)
    return "\n".join(chunks).strip()


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
    """Write the CSV into the sandbox session and describe it with pandas."""
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
    orders = staticmethod(list_orders)
    order = staticmethod(find_order)
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
        # Who is asking comes from the token the runtime verified, never from
        # the body. A request that reaches here without one did not come through
        # the runtime's authorizer.
        customer = customer_from(self.headers)
        if customer is None:
            self._send(401, {"error": "no verified caller"})
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
            self._handle_prompt(payload, prompt, customer)
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

    def _handle_prompt(self, payload, prompt, customer):
        """The routes from posts 02 and 03, now scoped to the verified customer."""
        session = payload.get("session", "default")
        workload_token = workload_token_from(self.headers)
        order = ORDER_RE.search(prompt)
        try:
            if prompt.lower().startswith("remember"):
                self.store(customer, session, prompt)
                self._send(200, {"result": "noted"})
            elif prompt.lower().startswith("recap"):
                self._send(200, {"result": self.history(customer, session)})
            elif MY_ORDERS_RE.search(prompt):
                self._send(200, {"result": json.loads(self.orders(customer, workload_token))})
            elif order:
                self._send(200, {"result": self.order(order.group(1), customer, workload_token)})
            else:
                self._send(200, {"result": self.search(customer, prompt)})
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
